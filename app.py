# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session, g
from werkzeug.security import generate_password_hash, check_password_hash
import db_utils
import sqlite3

app = Flask(__name__)
app.secret_key = "replace-this-with-a-secure-random-key"  # 実運用では安全な乱数にする
app.teardown_appcontext(db_utils.close_db)

# --- ユーザー周り ---
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        if not username or not password:
            flash("ユーザ名とパスワードを入力してください")
            return redirect(url_for("register"))
        db = db_utils.get_db()
        try:
            db.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, generate_password_hash(password))
            )
            db.commit()
            flash("登録しました。ログインしてください。")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("そのユーザ名は既に使われています")
            return redirect(url_for("register"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        db = db_utils.get_db()
        cur = db.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cur.fetchone()
        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["user_id"]
            session["username"] = user["username"]
            flash(f"ようこそ、{user['username']}さん")
            return redirect(url_for("products"))
        flash("ユーザ名かパスワードが違います")
        return redirect(url_for("login"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("ログアウトしました")
    return redirect(url_for("login"))

# login 必須デコレータ（簡易）
from functools import wraps
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("ログインしてください")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# --- 商品一覧 ---
@app.route("/")
@app.route("/products")
@login_required
def products():
    db = db_utils.get_db()
    cur = db.execute("""
        SELECT p.product_id, p.product_name, p.stock_quantity, p.min_stock, c.category_name
        FROM products p LEFT JOIN categories c ON p.category_id = c.rowid
        ORDER BY p.product_id
    """)
    items = cur.fetchall()
    return render_template("products.html", products=items)

# --- 入出庫フォーム ---
@app.route("/transaction", methods=["GET", "POST"])
@login_required
def transaction():
    db = db_utils.get_db()
    if request.method == "POST":
        product_id = int(request.form["product_id"])
        direction = request.form["direction"]  # "in" or "out"
        qty = int(request.form["quantity"])
        if qty <= 0:
            flash("数量は1以上を入力してください")
            return redirect(url_for("transaction"))
        if direction == "out":
            qty = -qty
        try:
            db_utils.add_transaction(product_id, session["user_id"], qty)
            flash("登録しました")
        except Exception as e:
            flash(str(e))
        return redirect(url_for("products"))
    # GET のときは商品リストを表示
    cur = db.execute("SELECT product_id, product_name, stock_quantity FROM products ORDER BY product_name")
    prods = cur.fetchall()
    return render_template("transaction_form.html", products=prods)

# --- 追加：在庫履歴（任意）---
@app.route("/history/<int:product_id>")
@login_required
def history(product_id):
    db = db_utils.get_db()
    cur = db.execute("""
        SELECT t.transaction_id, t.datetime, t.quantity, u.username
        FROM inventory_transactions t
        LEFT JOIN users u ON t.user_id = u.user_id
        WHERE t.product_id = ?
        ORDER BY t.datetime DESC
    """, (product_id,))
    rows = cur.fetchall()
    return render_template("layout_messages.html", rows=rows)

if __name__ == "__main__":
    app.run(debug=True)
