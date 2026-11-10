from app import database

conn = database.get_connection()
cols = [r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
conn.close()
print("must_change_password" in cols)
