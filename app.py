# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
import db_utils
import sqlite3
from functools import wraps

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

# --- 商品登録 ---
@app.route("/add_product", methods=["GET", "POST"])
@login_required
def add_product():
    db = db_utils.get_db()
    if request.method == "POST":
        name = request.form.get("product_name", "").strip()
        category_select = request.form.get("category_select", "")
        category_new = request.form.get("category_new", "").strip()
        try:
            initial_stock = int(request.form.get("initial_stock", "0"))
        except ValueError:
            initial_stock = 0
        try:
            min_stock = int(request.form.get("min_stock", "0"))
        except ValueError:
            min_stock = 0

        if not name:
            flash("商品名を入力してください")
            return redirect(url_for("add_product"))

        # カテゴリ決定（既存選択 or 新規作成）
        category_id = None
        if category_new:
            # 新規カテゴリを挿入して rowid を取得
            cur = db.execute("INSERT INTO categories (category_name) VALUES (?)", (category_new,))
            db.commit()
            category_id = cur.lastrowid
        elif category_select and category_select != "none":
            try:
                category_id = int(category_select)
            except ValueError:
                category_id = None

        # products に挿入
        cur = db.execute(
            "INSERT INTO products (category_id, product_name, stock_quantity, min_stock) VALUES (?, ?, ?, ?)",
            (category_id, name, initial_stock, min_stock)
        )
        db.commit()
        new_product_id = cur.lastrowid

        # 初期在庫があれば inventory_transactions に履歴を入れる（add_transaction を利用して在庫更新の履歴を確実に残す）
        # ただし、add_transaction は products の在庫も更新するため、ここでは既に stock_quantity を挿入済みなので、
        # 履歴だけを残す方法として直接INSERTします（日時はUTC ISO）。
        if initial_stock != 0:
            import datetime
            now = datetime.datetime.utcnow().isoformat()
            db.execute(
                "INSERT INTO inventory_transactions (product_id, datetime, user_id, quantity) VALUES (?, ?, ?, ?)",
                (new_product_id, now, session["user_id"], initial_stock)
            )
            db.commit()

        flash("商品を登録しました")
        return redirect(url_for("products"))

    # GET: 既存カテゴリ一覧を取得（rowidをidとして使う）
    cur = db.execute("SELECT rowid, category_name FROM categories ORDER BY category_name")
    cats = cur.fetchall()
    return render_template("add_product.html", categories=cats)

# --- 在庫を直接セット（差分をトランザクションとして残す） ---
@app.route("/set_stock/<int:product_id>", methods=["GET", "POST"])
@login_required
def set_stock(product_id):
    db = db_utils.get_db()
    cur = db.execute("SELECT product_id, product_name, stock_quantity FROM products WHERE product_id = ?", (product_id,))
    product = cur.fetchone()
    if product is None:
        flash("商品が見つかりません")
        return redirect(url_for("products"))

    if request.method == "POST":
        try:
            new_stock = int(request.form.get("new_stock", "0"))
        except ValueError:
            flash("正しい数値を入力してください")
            return redirect(url_for("set_stock", product_id=product_id))

        current_stock = product["stock_quantity"]
        delta = new_stock - current_stock
        if delta == 0:
            flash("在庫に変更はありません")
            return redirect(url_for("products"))

        try:
            # db_utils.add_transaction を使うと在庫更新とトランザクション挿入が行われる
            db_utils.add_transaction(product_id, session["user_id"], delta)
            flash("在庫を更新しました（履歴に反映されました）")
        except Exception as e:
            flash(str(e))
        return redirect(url_for("products"))

    return render_template("set_stock.html", product=product)

# --- 在庫履歴（任意）---
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
