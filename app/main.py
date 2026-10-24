import hashlib
import json
import os
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .db import connect, init
from .security import audit, may_access, verify_password
from .validator import MAX_BYTES, validate_shape

@asynccontextmanager
async def lifespan(app):
    init()
    yield

app = FastAPI(title='Partner Tool Portal', version='1.0.0', lifespan=lifespan, docs_url=None, redoc_url=None)
STATIC = Path(__file__).parent / 'static'
COOKIE = 'portal_session'
DUMMY_HASH = '00' * 16 + ':' + '00' * 64

@app.middleware('http')
async def protect(request, call_next):
    if request.method in ('POST', 'DELETE', 'PUT', 'PATCH'):
        if request.headers.get('x-portal-request') != '1':
            return JSONResponse({'detail': 'Missing request protection header.'}, status_code=403)
        origin = request.headers.get('origin')
        expected = os.environ.get('PORTAL_ORIGIN', str(request.base_url).rstrip('/'))
        if origin and origin != expected:
            return JSONResponse({'detail': 'Origin is not allowed.'}, status_code=403)
    response = await call_next(request)
    response.headers.update({'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY',
        'Referrer-Policy': 'no-referrer', 'Cache-Control': 'no-store',
        'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
    return response

def current_user(request: Request):
    token = request.cookies.get(COOKIE, '')
    with connect() as db:
        row = db.execute("""SELECT u.id,u.email,u.name,u.role,u.org FROM users u
            JOIN sessions s ON u.id=s.user_id WHERE s.token=? AND s.expires>?""",
            (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
    if not row: raise HTTPException(401, 'Please sign in.')
    return dict(row)

class Login(BaseModel):
    email: str = Field(max_length=160)
    password: str = Field(max_length=256)

class Submission(BaseModel):
    filename: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=MAX_BYTES)

@app.post('/api/login')
def login(body: Login):
    email, now = body.email.strip().lower(), time.time()
    with connect() as db:
        limit = db.execute('SELECT * FROM login_limits WHERE subject=?', (email,)).fetchone()
        if limit and limit['failures'] >= 5 and limit['until_time'] > now:
            raise HTTPException(429, 'Too many attempts. Try again in 15 minutes.')
        row = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        valid = verify_password(body.password, row['password'] if row else DUMMY_HASH)
        if not row or not valid:
            failures = limit['failures'] + 1 if limit and limit['until_time'] > now else 1
            db.execute('DELETE FROM login_limits WHERE subject=?', (email,))
            db.execute('INSERT INTO login_limits VALUES (?, ?, ?)', (email, failures, now + 900))
            failed = True
        else:
            failed = False
            db.execute('DELETE FROM login_limits WHERE subject=?', (email,))
            db.execute('DELETE FROM sessions WHERE expires<?', (now,))
            token = secrets.token_urlsafe(32)
            db.execute('INSERT INTO sessions VALUES (?, ?, ?)',
                (hashlib.sha256(token.encode()).hexdigest(), row['id'], now + 8 * 3600))
            audit(db, row, 'session.created')
    if failed: raise HTTPException(401, 'Invalid email or password.')
    response = JSONResponse({'ok': True})
    response.set_cookie(COOKIE, token, httponly=True, samesite='strict',
        secure=os.environ.get('COOKIE_SECURE', '0') == '1', max_age=8 * 3600)
    return response

@app.post('/api/logout')
def logout(request: Request, user=Depends(current_user)):
    with connect() as db:
        db.execute('DELETE FROM sessions WHERE token=?',
            (hashlib.sha256(request.cookies[COOKIE].encode()).hexdigest(),))
        audit(db, user, 'session.deleted')
    response = JSONResponse({'ok': True})
    response.delete_cookie(COOKIE)
    return response

@app.get('/api/me')
def me(user=Depends(current_user)): return user

def fetch_job(db, job_id, user):
    row = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
    if not row or not may_access(user, row): raise HTTPException(404, 'Job not found.')
    return dict(row)

def public_job(row):
    result = dict(row)
    for key in ('payload', 'worker', 'lease_until'): result.pop(key, None)
    result['report'] = json.loads(result['report']) if result['report'] else None
    return result

@app.get('/api/jobs')
def jobs(user=Depends(current_user)):
    with connect() as db:
        rows = db.execute('SELECT * FROM jobs' +
            (' WHERE org=?' if user['role'] == 'partner' else '') + ' ORDER BY created DESC LIMIT 200',
            (user['org'],) if user['role'] == 'partner' else ()).fetchall()
    return [public_job(r) for r in rows]

@app.post('/api/jobs', status_code=201)
async def submit(request: Request, user=Depends(current_user)):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_BYTES + 100_000: raise HTTPException(413, 'Upload exceeds 1 MB.')
    try:
        body = Submission.model_validate_json(raw)
        if len(body.content.encode('utf-8')) > MAX_BYTES: raise ValueError('Upload exceeds 1 MB.')
        if not body.filename.lower().endswith('.csv'): raise ValueError('Choose a .csv file.')
        validate_shape(body.content)
    except ValueError as exc:
        raise HTTPException(422, 'Invalid submission: check CSV format, column names, row count, filename, and 1 MB limit.') from exc
    now, job_id = time.time(), str(uuid.uuid4())
    with connect() as db:
        pending = db.execute("SELECT COUNT(*) AS n FROM jobs WHERE org=? AND status IN ('queued','running')", (user['org'],)).fetchone()['n']
        if pending >= 20: raise HTTPException(429, 'Your organization has 20 active jobs. Wait for completion.')
        db.execute("""INSERT INTO jobs
            (id,org,owner,filename,status,created,updated,attempts,payload)
            VALUES (?, ?, ?, ?, 'queued', ?, ?, 0, ?)""",
            (job_id, user['org'], user['id'], body.filename, now, now, body.content))
        audit(db, user, 'job.submitted', job_id)
        result = fetch_job(db, job_id, user)
    return public_job(result)

@app.get('/api/jobs/{job_id}')
def job(job_id: str, user=Depends(current_user)):
    with connect() as db: return public_job(fetch_job(db, job_id, user))

@app.post('/api/jobs/{job_id}/cancel')
def cancel(job_id: str, user=Depends(current_user)):
    with connect() as db:
        row = fetch_job(db, job_id, user)
        if row['status'] not in ('queued', 'running'): raise HTTPException(409, 'Only active jobs can be cancelled.')
        changed = db.execute("UPDATE jobs SET status='cancelled',updated=?,payload='' WHERE id=? AND status IN ('queued','running')", (time.time(), job_id)).rowcount
        if not changed: raise HTTPException(409, 'Job already finished.')
        audit(db, user, 'job.cancelled', job_id)
    return {'ok': True}

@app.get('/api/jobs/{job_id}/report')
def report(job_id: str, user=Depends(current_user)):
    with connect() as db:
        row = fetch_job(db, job_id, user)
        if row['status'] != 'completed': raise HTTPException(409, 'Report is not ready.')
        audit(db, user, 'report.downloaded', job_id)
    return Response(row['report'], media_type='application/json',
        headers={'Content-Disposition': f'attachment; filename="report-{job_id}.json"'})

@app.get('/api/audit')
def audit_log(user=Depends(current_user)):
    if user['role'] != 'admin': raise HTTPException(403, 'Administrator access required.')
    with connect() as db:
        return [dict(r) for r in db.execute('SELECT * FROM audit ORDER BY created DESC LIMIT 100').fetchall()]

@app.get('/health/live')
def live(): return {'status': 'ok'}

@app.get('/health/ready')
def ready():
    with connect() as db: db.execute('SELECT 1').fetchone()
    return {'status': 'ready'}

@app.get('/api/metrics')
def metrics(user=Depends(current_user)):
    if user['role'] not in ('admin', 'engineer'): raise HTTPException(403, 'Internal access required.')
    with connect() as db:
        rows = db.execute('SELECT status,COUNT(*) AS count FROM jobs GROUP BY status').fetchall()
    return {'jobs': {r['status']: r['count'] for r in rows}}

@app.get('/')
def home(): return FileResponse(STATIC / 'index.html')

app.mount('/static', StaticFiles(directory=STATIC), name='static')
