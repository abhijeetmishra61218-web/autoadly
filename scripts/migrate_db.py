import sqlite3

conn = sqlite3.connect("ad_bot.db")
cur = conn.cursor()
cur.execute("PRAGMA table_info(forum_topics)")
cols = [row[1] for row in cur.fetchall()]
if "closed" not in cols:
    cur.execute("ALTER TABLE forum_topics ADD COLUMN closed INTEGER DEFAULT 0")
    print("Added 'closed' column to forum_topics.")
else:
    print("'closed' column already exists.")
conn.commit()
conn.close()
