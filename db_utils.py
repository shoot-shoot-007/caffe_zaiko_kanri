# db_utils.py
import sqlite3
from flask import g
from datetime import datetime

DATABASE = "caffe_management_db.db"

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def add_transaction(product_id: int, user_id: int, quantity: int):
    """
    quantity: 正の数 = 入庫, 負の数 = 出庫
    """
    db = get_db()
    # 登録前に在庫確認（任意）
    cur = db.execute("SELECT stock_quantity FROM products WHERE product_id = ?", (product_id,))
    row = cur.fetchone()
    if row is None:
        raise ValueError("product not found")
    new_stock = row["stock_quantity"] + quantity
    if new_stock < 0:
        raise ValueError("在庫不足: 操作をキャンセルします")
    # 在庫更新
    db.execute("UPDATE products SET stock_quantity = ? WHERE product_id = ?", (new_stock, product_id))
    # トランザクション挿入（ISO形式日時）
    now = datetime.utcnow().isoformat()
    db.execute(
        "INSERT INTO inventory_transactions (product_id, datetime, user_id, quantity) VALUES (?, ?, ?, ?)",
        (product_id, now, user_id, quantity)
    )
    db.commit()
