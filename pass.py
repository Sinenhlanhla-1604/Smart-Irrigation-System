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