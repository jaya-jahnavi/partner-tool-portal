import hashlib
import hmac
import secrets
import time
import uuid

def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return salt + ':' + digest

def verify_password(password, stored):
    salt, expected = stored.split(':')
    actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return hmac.compare_digest(actual, expected)

def audit(db, user, action, job_id=None):
    db.execute('INSERT INTO audit VALUES (?, ?, ?, ?, ?, ?)',
        (str(uuid.uuid4()), time.time(), user['email'], action, user['org'], job_id))

def may_access(user, job):
    return user['role'] in ('admin', 'engineer') or user['org'] == job['org']
