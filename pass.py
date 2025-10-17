"""Utility script to hash plaintext passwords and update Users table.

Purpose:
- Connects to the local PostgreSQL database (SGS_Database).
- Generates Werkzeug password hashes from plaintext values.
- Updates the Users.password field for specified emails.

Intended use:
- For local development / maintenance when you need to quickly reset or
  migrate sample user passwords to hashed values.
- Edit the `raw` variables to the desired plaintext password(s) and run:
      python pass.py

Security notes:
- Do NOT run this on production databases without proper safeguards.
- Avoid committing plaintext passwords or credentials into source control.
- Prefer secure admin workflows for password resets in production.
"""

from werkzeug.security import generate_password_hash
import psycopg2

conn = psycopg2.connect(host='127.0.0.1', database='SGS_Database', user='postgres', password='123')
cur = conn.cursor()

raw = '123'  # change to the raw password you want the user to use
raw2 = 'Iamafarmer'
hashed = generate_password_hash(raw)
hashed2 = generate_password_hash(raw2)
cur.execute("UPDATE Users SET password = %s WHERE email = %s", (hashed, 'sine@eg.com'))
cur.execute("UPDATE Users SET password = %s WHERE email = %s", (hashed2, 'ashock@example.com'))

conn.commit()
cur.close()
conn.close()
print('✅ Password updated to hashed value')