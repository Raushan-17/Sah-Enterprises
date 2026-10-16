import os, sqlite3, json, time
from functools import wraps
from flask import Flask, request, session, redirect, url_for, render_template_string, g, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret")
DB = os.environ.get("DB_PATH", "orders.db")
OWNER_PHONE = os.environ.get("OWNER_PHONE", "9999999999")      # owner login
OWNER_PASSWORD = os.environ.get("OWNER_PASSWORD", "admin123")  # CHANGE THIS
COMPANY = os.environ.get("COMPANY_NAME", "My Company")

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB); g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close(e):
    d = g.pop("db", None)
    if d: d.close()

def init():
    c = sqlite3.connect(DB)
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, shop TEXT, village TEXT, phone TEXT UNIQUE, pw TEXT);
    CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, name TEXT, price REAL, unit TEXT, active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, user_id INTEGER, items TEXT, total REAL, status TEXT DEFAULT 'New', ts INTEGER);
    """); c.commit(); c.close()
init()

def login_required(owner=False):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            if "uid" not in session and not session.get("owner"):
                return redirect(url_for("login"))
            if owner and not session.get("owner"):
                return redirect(url_for("home"))
            return f(*a, **k)
        return w
    return deco

BASE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{{company}}</title>
<style>
body{margin:0;font-family:system-ui,sans-serif;background:#fafaf7;color:#1d2a1f}
header{background:#1b7a3d;color:#fff;padding:14px 16px;display:flex;justify-content:space-between;align-items:center}
header a{color:#fff;margin-left:12px;font-size:14px}
main{max-width:680px;margin:0 auto;padding:12px}
.c{background:#fff;border:1px solid #e3e3dc;border-radius:12px;padding:12px;margin-bottom:10px}
.r{display:flex;justify-content:space-between;align-items:center;gap:8px}
input,select{padding:10px;border:1px solid #ccc;border-radius:8px;font:inherit;width:100%;margin:4px 0}
button{background:#1b7a3d;color:#fff;border:0;border-radius:8px;padding:10px 14px;font:inherit}
.q{width:70px}.m{color:#667;font-size:13px}.s{border:1px solid #1b7a3d;color:#1b7a3d;border-radius:99px;padding:2px 8px;font-size:12px}
.f{background:#fde8e8;padding:8px;border-radius:8px;margin-bottom:8px}
</style></head><body>
<header><b>{{company}}</b><span>
{% if session.owner %}<a href="/owner/orders">Orders</a><a href="/owner/products">Products</a>
{% elif session.uid %}<a href="/">Shop</a><a href="/orders">My Orders</a>{% endif %}
{% if session.uid or session.owner %}<a href="/logout">Logout</a>{% endif %}</span></header>
<main>{% for m in get_flashed_messages() %}<div class="f">{{m}}</div>{% endfor %}
{{body|safe}}</main></body></html>"""

def page(body_tpl, **ctx):
    body = render_template_string(body_tpl, **ctx)
    return render_template_string(BASE, body=body, company=COMPANY)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        try:
            db().execute("INSERT INTO users(shop,village,phone,pw) VALUES(?,?,?,?)",
                (f["shop"].strip(), f["village"].strip(), f["phone"].strip(), generate_password_hash(f["password"])))
            db().commit(); flash("Account created. Please log in."); return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("This phone number is already registered.")
    return page("""<div class="c"><h3>Create account</h3><form method="post">
    <input name="shop" placeholder="Shop name" required><input name="village" placeholder="Village" required>
    <input name="phone" placeholder="Mobile number" required><input name="password" type="password" placeholder="Password" required>
    <button>Register</button></form><p><a href="/login">Already have an account? Login</a></p></div>""")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ph, pw = request.form["phone"].strip(), request.form["password"]
        if ph == OWNER_PHONE and pw == OWNER_PASSWORD:
            session.clear(); session["owner"] = True; return redirect("/owner/orders")
        u = db().execute("SELECT * FROM users WHERE phone=?", (ph,)).fetchone()
        if u and check_password_hash(u["pw"], pw):
            session.clear(); session["uid"] = u["id"]; return redirect("/")
        flash("Wrong phone number or password.")
    return page("""<div class="c"><h3>Login</h3><form method="post">
    <input name="phone" placeholder="Mobile number" required><input name="password" type="password" placeholder="Password" required>
    <button>Login</button></form><p><a href="/register">New shopkeeper? Create account</a></p></div>""")

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("login"))

@app.route("/", methods=["GET", "POST"])
@login_required()
def home():
    if session.get("owner"): return redirect("/owner/orders")
    prods = db().execute("SELECT * FROM products WHERE active=1 ORDER BY name").fetchall()
    if request.method == "POST":
        items, total = [], 0
        for p in prods:
            q = int(request.form.get(f"q{p['id']}") or 0)
            if q > 0:
                items.append({"name": p["name"], "price": p["price"], "unit": p["unit"], "qty": q}); total += q * p["price"]
        if not items:
            flash("Please select at least one item.")
        else:
            db().execute("INSERT INTO orders(user_id,items,total,ts) VALUES(?,?,?,?)", (session["uid"], json.dumps(items), total, int(time.time())))
            db().commit(); flash("Order placed successfully!"); return redirect("/orders")
    return page("""<form method="post">{% if not prods %}<div class="c">No products yet.</div>{% endif %}
    {% for p in prods %}<div class="c r"><div><b>{{p['name']}}</b><div class="m">₹{{p['price']|round(2)}} / {{p['unit']}}</div></div>
    <input class="q" type="number" min="0" name="q{{p['id']}}" placeholder="Qty"></div>{% endfor %}
    {% if prods %}<button style="width:100%">Place Order</button>{% endif %}</form>""", prods=prods)

def parse(rows):
    return [dict(r, items=json.loads(r["items"]), when=time.strftime("%d %b %Y, %H:%M", time.localtime(r["ts"]))) for r in rows]

@app.route("/orders")
@login_required()
def my_orders():
    rows = db().execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC", (session["uid"],)).fetchall()
    return page(ORDERS, orders=parse(rows), owner=False)

ORDERS = """{% if not orders %}<div class="c">No orders yet.</div>{% endif %}
{% for o in orders %}<div class="c"><div class="r"><b>{% if owner %}{{o['shop']}} • {{o['village']}}{% else %}Order #{{o['id']}}{% endif %}</b><span class="s">{{o['status']}}</span></div>
{% if owner %}<div class="m">📞 {{o['phone']}}</div>{% endif %}<div class="m">{{o['when']}}</div>
{% for i in o['items'] %}<div>{{i['name']}} × {{i['qty']}} = ₹{{(i['price']*i['qty'])|round(2)}}</div>{% endfor %}
<b>Total: ₹{{o['total']|round(2)}}</b>
{% if owner %}<form method="post" action="/owner/status/{{o['id']}}" class="r" style="margin-top:8px">
<select name="status">{% for s in ['New','Confirmed','Delivered','Cancelled'] %}<option {{'selected' if s==o['status']}}>{{s}}</option>{% endfor %}</select><button>Update</button></form>{% endif %}</div>{% endfor %}"""

@app.route("/owner/orders")
@login_required(owner=True)
def owner_orders():
    rows = db().execute("SELECT o.*, u.shop, u.village, u.phone FROM orders o JOIN users u ON u.id=o.user_id ORDER BY o.id DESC").fetchall()
    return page(ORDERS, orders=parse(rows), owner=True)

@app.route("/owner/status/<int:oid>", methods=["POST"])
@login_required(owner=True)
def status(oid):
    db().execute("UPDATE orders SET status=? WHERE id=?", (request.form["status"], oid)); db().commit()
    return redirect("/owner/orders")

@app.route("/owner/products", methods=["GET", "POST"])
@login_required(owner=True)
def products():
    if request.method == "POST":
        f = request.form
        db().execute("INSERT INTO products(name,price,unit) VALUES(?,?,?)", (f["name"].strip(), float(f["price"]), f["unit"].strip())); db().commit()
        return redirect("/owner/products")
    prods = db().execute("SELECT * FROM products WHERE active=1 ORDER BY name").fetchall()
    return page("""<div class="c"><h3>Add product</h3><form method="post"><input name="name" placeholder="Product name" required>
    <input name="price" type="number" step="0.01" placeholder="Price (₹)" required><input name="unit" placeholder="Unit (packet, bottle, kg)" required><button>Add</button></form></div>
    {% for p in prods %}<div class="c r"><div><b>{{p['name']}}</b><div class="m">₹{{p['price']|round(2)}} / {{p['unit']}}</div></div>
    <form method="post" action="/owner/delete/{{p['id']}}"><button style="background:#b33">Delete</button></form></div>{% endfor %}""", prods=prods)

@app.route("/owner/delete/<int:pid>", methods=["POST"])
@login_required(owner=True)
def delete(pid):
    db().execute("UPDATE products SET active=0 WHERE id=?", (pid,)); db().commit()
    return redirect("/owner/products")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
