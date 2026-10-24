"""Separate worker: atomic claims, expiring leases, bounded retries, stale-worker fencing."""
import json
import logging
import signal
import time
import uuid
from .db import connect, init
from .validator import analyze

log = logging.getLogger('portal.worker')
LEASE_SECONDS = 60
MAX_ATTEMPTS = 3
STOP = False

def run_once():
    now, worker = time.time(), str(uuid.uuid4())
    with connect() as db:
        db.execute("""UPDATE jobs SET status='failed',error='Worker lease expired after 3 attempts.',
            updated=?,payload='' WHERE status='running' AND lease_until<? AND attempts>=?""", (now, now, MAX_ATTEMPTS))
        row = db.execute("""SELECT * FROM jobs WHERE
            (status='queued' OR (status='running' AND lease_until<?)) AND attempts<?
            ORDER BY created LIMIT 1""", (now, MAX_ATTEMPTS)).fetchone()
        if not row: return False
        row = dict(row)
        claimed = db.execute("""UPDATE jobs SET status='running',worker=?,lease_until=?,
            attempts=attempts+1,updated=? WHERE id=? AND
            (status='queued' OR (status='running' AND lease_until<?)) AND attempts<?""",
            (worker, now + LEASE_SECONDS, now, row['id'], now, MAX_ATTEMPTS)).rowcount
        if not claimed: return False
    try:
        report = json.dumps(analyze(row['payload']), allow_nan=False)
        with connect() as db:
            db.execute("""UPDATE jobs SET status='completed',report=?,payload='',updated=?,error=NULL
                WHERE id=? AND worker=? AND status='running' AND lease_until>?""",
                (report, time.time(), row['id'], worker, time.time()))
        log.info('job_finished id=%s', row['id'])
    except Exception:
        log.exception('job_failed id=%s', row['id'])
        with connect() as db:
            terminal = row['attempts'] + 1 >= MAX_ATTEMPTS
            db.execute("""UPDATE jobs SET status=?,error=?,updated=?,payload=CASE WHEN ? THEN '' ELSE payload END
                WHERE id=? AND worker=? AND status='running' AND lease_until>?""",
                ('failed' if terminal else 'queued', 'Processing failed; see worker logs.', time.time(),
                 int(terminal), row['id'], worker, time.time()))
    return True

def stop(*_):
    global STOP
    STOP = True

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    init()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not STOP:
        try:
            if not run_once(): time.sleep(0.5)
        except Exception:
            log.exception('worker_poll_failed')
            time.sleep(2)
