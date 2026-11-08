import sqlite3
DB = r'd:\DACS2\backend\cinai.db'
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
for t in cur.fetchall():
    cur.execute(f"SELECT COUNT(*) FROM {t[0]}")
    print(t[0], ':', cur.fetchone()[0], 'rows')
conn.close()
