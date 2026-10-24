"""DB-API persistence: SQLite locally and MySQL in Docker Compose."""
import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager

DATA = Path(os.environ.get('PORTAL_DATA', '.local')).resolve()
DATA.mkdir(parents=True, exist_ok=True)

@contextmanager
def connect():
    if os.environ.get('DB_ENGINE') == 'mysql':
        import pymysql
        db = pymysql.connect(host=os.environ.get('DB_HOST', 'db'),
            user=os.environ.get('DB_USER', 'portal'), password=os.environ['DB_PASSWORD'],
            database=os.environ.get('DB_NAME', 'portal'),
            cursorclass=pymysql.cursors.DictCursor, autocommit=False)
    else:
        db = sqlite3.connect(DATA / 'portal.db', timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA journal_mode=WAL')
    try:
        yield Connection(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

class Connection:
    def __init__(self, db): self.db = db
    def execute(self, sql, params=()):
        cur = self.db.cursor()
        cur.execute(sql.replace('?', '%s') if os.environ.get('DB_ENGINE') == 'mysql' else sql, params)
        return cur

def init():
    statements = [
        """CREATE TABLE IF NOT EXISTS users (
            id VARCHAR(36) PRIMARY KEY, email VARCHAR(160) UNIQUE NOT NULL,
            name VARCHAR(100) NOT NULL, role VARCHAR(20) NOT NULL,
            org VARCHAR(80) NOT NULL, password VARCHAR(256) NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS sessions (
            token VARCHAR(64) PRIMARY KEY, user_id VARCHAR(36) NOT NULL,
            expires DOUBLE NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id))""",
        """CREATE TABLE IF NOT EXISTS jobs (
            id VARCHAR(36) PRIMARY KEY, org VARCHAR(80) NOT NULL,
            owner VARCHAR(36) NOT NULL, filename VARCHAR(160) NOT NULL,
            status VARCHAR(20) NOT NULL, created DOUBLE NOT NULL,
            updated DOUBLE NOT NULL, attempts INTEGER NOT NULL,
            lease_until DOUBLE, worker VARCHAR(36), error TEXT,
            report TEXT, payload MEDIUMTEXT NOT NULL,
            FOREIGN KEY(owner) REFERENCES users(id))""",
        """CREATE TABLE IF NOT EXISTS audit (
            id VARCHAR(36) PRIMARY KEY, created DOUBLE NOT NULL,
            actor VARCHAR(160) NOT NULL, action VARCHAR(60) NOT NULL,
            org VARCHAR(80) NOT NULL, job_id VARCHAR(36))""",
        """CREATE TABLE IF NOT EXISTS login_limits (
            subject VARCHAR(160) PRIMARY KEY, failures INTEGER NOT NULL,
            until_time DOUBLE NOT NULL)""",
    ]
    with connect() as db:
        for sql in statements: db.execute(sql)
