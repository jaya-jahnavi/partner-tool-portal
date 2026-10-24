"""Integration tests against a real HTTP server and isolated SQLite database."""
import concurrent.futures
import http.cookiejar
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

class PortalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / '.local').mkdir(exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=ROOT / '.local')
        os.environ['PORTAL_DATA'] = cls.temp.name
        os.environ.pop('DB_ENGINE', None)
        subprocess.run([sys.executable, '-m', 'app.seed'], cwd=ROOT, check=True, capture_output=True)
        cls.accounts = json.loads((Path(cls.temp.name) / 'demo-credentials.json').read_text())
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            cls.port = sock.getsockname()[1]
        cls.base = f'http://127.0.0.1:{cls.port}'
        cls.process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app',
            '--host', '127.0.0.1', '--port', str(cls.port)], cwd=ROOT,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                urllib.request.urlopen(cls.base + '/health/ready', timeout=1)
                break
            except Exception: time.sleep(0.1)
        else:
            cls.process.terminate()
            raise RuntimeError('Test server did not start.')
        from app import worker
        from app.db import connect
        cls.worker = worker
        cls.connect = staticmethod(connect)

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=10)
        cls.temp.cleanup()

    def setUp(self):
        with self.connect() as db:
            for table in ('jobs', 'sessions', 'audit', 'login_limits'):
                db.execute('DELETE FROM ' + table)

    def client(self):
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(self, client, path, method='GET', body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method,
            headers={'Content-Type':'application/json', 'X-Portal-Request':'1', **(headers or {})})
        try: response = client.open(request, timeout=10)
        except urllib.error.HTTPError as exc: response = exc
        raw = response.read()
        return response.status, json.loads(raw) if raw else None, response.headers

    def login(self, email):
        client = self.client()
        account = next(a for a in self.accounts if a['email'] == email)
        status, _, headers = self.request(client, '/api/login', 'POST', account)
        self.assertEqual(status, 200)
        self.assertIn('HttpOnly', headers['Set-Cookie'])
        self.assertIn('SameSite=strict', headers['Set-Cookie'])
        return client

    def submit(self, client, content='x,y\n1,2\n1,2\n3,\n', filename='sample.csv'):
        status, job, _ = self.request(client, '/api/jobs', 'POST', {'filename':filename,'content':content})
        self.assertEqual(status, 201, job)
        self.assertNotIn('payload', job)
        return job

    def test_authentication_csrf_and_session_revocation(self):
        client = self.client()
        self.assertEqual(self.request(client, '/api/jobs')[0], 401)
        self.assertEqual(self.request(client, '/api/login', 'POST', {}, {'X-Portal-Request':''})[0], 403)
        self.assertEqual(self.request(client, '/api/login', 'POST', {}, {'Origin':'https://evil.example'})[0], 403)
        client = self.login('partner.a@example.test')
        self.assertEqual(self.request(client, '/api/me')[1]['org'], 'Atlas Labs')
        self.assertEqual(self.request(client, '/api/logout', 'POST')[0], 200)
        self.assertEqual(self.request(client, '/api/jobs')[0], 401)

    def test_end_to_end_report_and_payload_deletion(self):
        client = self.login('partner.a@example.test')
        job = self.submit(client)
        self.assertTrue(self.worker.run_once())
        status, result, _ = self.request(client, '/api/jobs/' + job['id'])
        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['report']['duplicates'], 1)
        self.assertEqual(result['report']['missing_cells'], 1)
        self.assertEqual(result['report']['rows'], 3)
        status, report, headers = self.request(client, '/api/jobs/' + job['id'] + '/report')
        self.assertEqual(status, 200)
        self.assertEqual(report, result['report'])
        self.assertIn('attachment', headers['Content-Disposition'])
        with self.connect() as db:
            self.assertEqual(db.execute('SELECT payload FROM jobs WHERE id=?',(job['id'],)).fetchone()['payload'], '')

    def test_cross_tenant_list_detail_report_cancel_are_denied(self):
        a, b = self.login('partner.a@example.test'), self.login('partner.b@example.test')
        job = self.submit(a)
        self.assertEqual(self.request(b, '/api/jobs')[1], [])
        for suffix in ('', '/report'):
            self.assertEqual(self.request(b, '/api/jobs/' + job['id'] + suffix)[0], 404)
        self.assertEqual(self.request(b, '/api/jobs/' + job['id'] + '/cancel', 'POST')[0], 404)
        self.worker.run_once()
        self.assertEqual(self.request(b, '/api/jobs/' + job['id'] + '/report')[0], 404)

    def test_internal_roles_and_admin_only_audit(self):
        partner = self.login('partner.a@example.test')
        self.submit(partner)
        engineer, admin = self.login('engineer@example.test'), self.login('admin@example.test')
        self.assertEqual(len(self.request(engineer, '/api/jobs')[1]), 1)
        self.assertEqual(self.request(partner, '/api/metrics')[0], 403)
        self.assertEqual(self.request(engineer, '/api/metrics')[1]['jobs']['queued'], 1)
        self.assertEqual(self.request(engineer, '/api/audit')[0], 403)
        self.assertEqual(self.request(partner, '/api/audit')[0], 403)
        actions = [r['action'] for r in self.request(admin, '/api/audit')[1]]
        self.assertIn('job.submitted', actions)

    def test_invalid_inputs_and_upload_limits(self):
        client = self.login('partner.a@example.test')
        for content in ('', 'x,x\n1,2', 'x,y\n1', 'x,y\n', 'x,y\n"unterminated,2'):
            status, _, _ = self.request(client, '/api/jobs', 'POST', {'filename':'bad.csv','content':content})
            self.assertEqual(status, 422, content)
        self.assertEqual(self.request(client, '/api/jobs', 'POST', {'filename':'file.exe','content':'x\n1'})[0], 422)
        self.assertEqual(self.request(client, '/api/jobs', 'POST', {'filename':'big.csv','content':'x' * 1_100_001})[0], 413)
        self.assertEqual(self.request(client, '/api/jobs', 'POST', {'filename':'rows.csv','content':'x\n' + '1\n'*10_001})[0], 422)

    def test_cancelled_jobs_do_not_run(self):
        client = self.login('partner.a@example.test')
        job = self.submit(client)
        self.assertEqual(self.request(client, '/api/jobs/' + job['id'] + '/cancel', 'POST')[0], 200)
        self.assertFalse(self.worker.run_once())
        self.assertEqual(self.request(client, '/api/jobs/' + job['id'])[1]['status'], 'cancelled')
        self.assertEqual(self.request(client, '/api/jobs/' + job['id'] + '/report')[0], 409)

    def test_expired_lease_is_recovered_and_final_attempt_terminates(self):
        client = self.login('partner.a@example.test')
        job = self.submit(client)
        with self.connect() as db:
            db.execute("UPDATE jobs SET status='running',attempts=1,worker='dead',lease_until=? WHERE id=?", (time.time()-5,job['id']))
        self.worker.run_once()
        result = self.request(client, '/api/jobs/' + job['id'])[1]
        self.assertEqual((result['status'],result['attempts']), ('completed',2))
        other = self.submit(client)
        with self.connect() as db:
            db.execute("UPDATE jobs SET status='running',attempts=3,lease_until=? WHERE id=?", (time.time()-5,other['id']))
        self.worker.run_once()
        self.assertEqual(self.request(client, '/api/jobs/' + other['id'])[1]['status'], 'failed')

    def test_processing_failure_retries_at_most_three_times(self):
        client = self.login('partner.a@example.test')
        job = self.submit(client)
        with patch.object(self.worker, 'analyze', side_effect=RuntimeError('injected failure')):
            with patch.object(self.worker.log, 'exception'):
                for _ in range(3): self.worker.run_once()
        self.assertFalse(self.worker.run_once())
        result = self.request(client, '/api/jobs/' + job['id'])[1]
        self.assertEqual((result['status'],result['attempts']), ('failed',3))

    def test_stale_worker_cannot_overwrite_cancellation(self):
        client = self.login('partner.a@example.test')
        job = self.submit(client)
        original = self.worker.analyze
        def cancel_during_run(payload):
            self.assertEqual(self.request(client, '/api/jobs/' + job['id'] + '/cancel','POST')[0], 200)
            return original(payload)
        with patch.object(self.worker, 'analyze', side_effect=cancel_during_run):
            self.worker.run_once()
        self.assertEqual(self.request(client, '/api/jobs/' + job['id'])[1]['status'], 'cancelled')

    def test_competing_workers_do_not_duplicate_processing(self):
        client = self.login('partner.a@example.test')
        job = self.submit(client)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.worker.run_once(), range(2)))
        self.assertEqual(sum(results), 1)
        result = self.request(client, '/api/jobs/' + job['id'])[1]
        self.assertEqual((result['status'], result['attempts']), ('completed', 1))

    def test_failed_login_attempts_are_persisted(self):
        client = self.client()
        body = {'email':'partner.a@example.test','password':'incorrect'}
        for _ in range(5): self.assertEqual(self.request(client, '/api/login','POST',body)[0], 401)
        self.assertEqual(self.request(client, '/api/login','POST',body)[0], 429)

class ValidatorTests(unittest.TestCase):
    def test_clean_dataset_and_nonfinite_numbers(self):
        from app.validator import analyze
        clean = analyze('x,y\n1,blue\n2,red\n')
        self.assertEqual(clean['verdict'], 'passed')
        self.assertEqual(clean['columns'][0]['max'], 2)
        nonfinite = analyze('x\nNaN\nInfinity\n')
        self.assertEqual(nonfinite['columns'][0]['type'], 'text')
        json.dumps(nonfinite, allow_nan=False)

if __name__ == '__main__': unittest.main()
