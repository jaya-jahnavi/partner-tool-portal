"""Explicit demo initialization; never run against production."""
import json
import secrets
import uuid
from .db import DATA, connect, init
from .security import hash_password

def seed():
    init()
    accounts = []
    with connect() as db:
        for email, name, role, org in [
            ('admin@example.test', 'Alex Morgan', 'admin', 'Internal'),
            ('engineer@example.test', 'Jordan Lee', 'engineer', 'Internal'),
            ('partner.a@example.test', 'Sam Chen', 'partner', 'Atlas Labs'),
            ('partner.b@example.test', 'Riley Park', 'partner', 'Northstar Devices')]:
            if db.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone(): continue
            password = secrets.token_urlsafe(16)
            db.execute('INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)',
                (str(uuid.uuid4()), email, name, role, org, hash_password(password)))
            accounts.append({'email': email, 'password': password, 'role': role})
    if accounts:
        path = DATA / 'demo-credentials.json'
        path.write_text(json.dumps(accounts, indent=2), encoding='utf-8')
        print(f'Demo accounts created. Credentials: {path}')
    else: print('Accounts already exist; no passwords changed.')

if __name__ == '__main__': seed()
