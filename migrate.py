import sqlite3
import traceback

print("Starting DB migration...")
conn = sqlite3.connect('favorite-movies.db')
c = conn.cursor()

commands = [
    "ALTER TABLE user ADD COLUMN bio VARCHAR(500)",
    "ALTER TABLE user ADD COLUMN avatar_url VARCHAR(500)",
    "ALTER TABLE movie ADD COLUMN custom_tags VARCHAR(250)",
    "ALTER TABLE book ADD COLUMN custom_tags VARCHAR(250)",
    """
    CREATE TABLE IF NOT EXISTS followers (
        follower_id INTEGER NOT NULL,
        followed_id INTEGER NOT NULL,
        FOREIGN KEY(follower_id) REFERENCES user(id),
        FOREIGN KEY(followed_id) REFERENCES user(id)
    )
    """
]

for cmd in commands:
    try:
        c.execute(cmd)
        print(f"Executed: {cmd}")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
            print(f"Skipped (already exists): {cmd.strip()}")
        else:
            print(f"Error on {cmd}: {e}")

conn.commit()
conn.close()
print("Migration finished!")
