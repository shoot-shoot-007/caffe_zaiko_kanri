# hash_existing_passwords.py
# 既存 users テーブルの password 列をハッシュ化する簡単スクリプト
# 実行前に DB のバックアップを必ず取ってください。

import sqlite3
from werkzeug.security import generate_password_hash
import re

DB = "caffe_management_db.db"

def looks_like_werkzeug_hash(s: str) -> bool:
    # werkzeug のデフォルトは "pbkdf2:sha256:..." のような形式になります。
    # ここでは簡易判定：コロンが含まれ、長めの文字列ならハッシュとみなす。
    if not isinstance(s, str):
        return False
    if ":" in s and len(s) > 30:
        return True
    return False

def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT user_id, username, password FROM users")
    rows = cur.fetchall()

    updated = 0
    for r in rows:
        pw = r["password"]
        uid = r["user_id"]
        username = r["username"]
        if pw is None:
            print(f"[SKIP] user_id={uid} ({username}) password is NULL")
            continue
        if looks_like_werkzeug_hash(pw):
            print(f"[OK]   user_id={uid} ({username}) already hashed — skipping")
            continue
        # ここで平文と見なしてハッシュ化
        hashed = generate_password_hash(pw)
        cur.execute("UPDATE users SET password = ? WHERE user_id = ?", (hashed, uid))
        updated += 1
        print(f"[HASH] user_id={uid} ({username}) -> hashed")

    conn.commit()
    conn.close()
    print(f"Done. {updated} passwords hashed.")

if __name__ == "__main__":
    main()
