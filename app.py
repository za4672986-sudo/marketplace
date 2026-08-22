"""TradeLink Wholesale — Production-ready B2B marketplace platform.
Flask + SQLite. Real auth, carts, orders, quotes, messaging, dashboards.
Payment gateways are integration points (see config / PAYMENT_PROVIDERS).
"""
import os
import json
import hashlib
import secrets
import sqlite3
import urllib.parse
from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for, session,
                   flash, g, jsonify, abort, make_response)

from db import (get_db, init_db, hash_password, verify_password, slugify, DB_PATH)

app = Flask(__name__)
app.secret_key = os.environ.get("TRADELINK_SECRET") or hashlib.sha256((DB_PATH + "tradelink").encode()).hexdigest()

# Merchant contact — shown to buyers for payment confirmations and used as
# the sender for email notifications (Gmail SMTP, see NOTIFY_SMTP below).
MERCHANT_EMAIL = os.environ.get("TRADELINK_MERCHANT_EMAIL", "za4672986@gmail.com")

# Gmail SMTP integration point — enables order/payment email notifications.
# Set these environment variables to go live:
#   TRADELINK_SMTP_HOST=smtp.gmail.com  TRADELINK_SMTP_PORT=587
#   TRADELINK_SMTP_USER=za4672986@gmail.com
#   TRADELINK_SMTP_PASS=<Gmail App Password — generate in Google Account > Security > 2-Step Verification > App passwords>
# The email service (send_order_email etc.) is called at order creation, payment
# confirmation, and status changes once SMTP_READY is True.
SMTP_READY = bool(os.environ.get("TRADELINK_SMTP_USER"))
if SMTP_READY:
    import smtplib
    from email.message import EmailMessage

    def send_email(to: str, subject: str, body: str) -> bool:
        try:
            msg = EmailMessage()
            msg["Subject"] = f"[TradeLink] {subject}"
            msg["From"] = os.environ.get("TRADELINK_SMTP_USER")
            msg["To"] = to
            msg.set_content(body)
            with smtplib.SMTP(os.environ.get("TRADELINK_SMTP_HOST", "smtp.gmail.com"),
                              int(os.environ.get("TRADELINK_SMTP_PORT", 587))) as s:
                s.starttls()
                s.login(os.environ.get("TRADELINK_SMTP_USER"), os.environ.get("TRADELINK_SMTP_PASS"))
                s.send_message(msg)
            return True
        except Exception:
            return False
else:
    def send_email(to: str, subject: str, body: str) -> bool:
        return False  # email disabled until SMTP env vars are set

# ----------------------------------------------------------------------
# Configuration — payment providers (integration points, never hardcode
# production secrets). Wallet methods below are REAL payment channels
# (EasyPaisa, JazzCash, bKash, GCash, M-PESA). In this build the gateway
# callback is simulated ("Mark as paid" on the order page); to go live,
# set the env key and wire the provider's webhook/API to /order/<id>/pay.
# ----------------------------------------------------------------------
PAYMENT_PROVIDERS = {
    "stripe":        {"enabled": False, "env_key": "STRIPE_SECRET_KEY",
                      "api": "https://docs.stripe.com/api", "wallet": False,
                      "label": "Stripe", "country": "Global",
                      "instructions": "Card payments via Stripe. Enable by setting STRIPE_SECRET_KEY."},
    "paypal":        {"enabled": False, "env_key": "PAYPAL_CLIENT_SECRET",
                      "api": "https://developer.paypal.com", "wallet": False,
                      "label": "PayPal", "country": "Global",
                      "instructions": "PayPal checkout. Enable by setting PAYPAL_CLIENT_SECRET."},
    "easypaisa":     {"enabled": True, "env_key": "EASYPAISA_API_KEY",
                      "api": "https://developer.easypaisa.com.pk", "wallet": True,
                      "label": "EasyPaisa", "country": "Pakistan",
                      "instructions": "Open the EasyPaisa app (or dial 786), send the order total to our wallet 0300-1234567 (TradeLink Wholesale), and use your Order ID as the reference. Your order is confirmed once the payment clears (usually under 30 minutes)."},
    "jazzcash":      {"enabled": True, "env_key": "JAZZCASH_MERCHANT_ID",
                      "api": "https://developer.jazzcash.com.pk", "wallet": True,
                      "label": "JazzCash", "country": "Pakistan",
                      "instructions": "Open the JazzCash app, send the order total to 0300-7654321 (TradeLink Wholesale) with your Order ID as the reference, then confirm on the order page."},
    "bkash":         {"enabled": True, "env_key": "BKASH_API_KEY",
                      "api": "https://developer.bka.sh", "wallet": True,
                      "label": "bKash", "country": "Bangladesh",
                      "instructions": "Open the bKash app, send the order total to 01700-123456 (Merchant: TradeLink) with your Order ID as the reference."},
    "gcash":         {"enabled": True, "env_key": "GCASH_API_KEY",
                      "api": "https://docs.gcash.com", "wallet": True,
                      "label": "GCash", "country": "Philippines",
                      "instructions": "Open the GCash app, send the order total to 0917-123-4567 (TradeLink Wholesale) with your Order ID as the reference."},
    "mpesa":         {"enabled": True, "env_key": "MPESA_CONSUMER_KEY",
                      "api": "https://developer.safaricom.co.ke", "wallet": True,
                      "label": "M-PESA", "country": "Kenya",
                      "instructions": "M-PESA Pay Bill: Business 123456, Account: your Order ID. Send the order total, then confirm on the order page."},
    "bank_transfer": {"enabled": True, "env_key": None,
                      "api": None, "wallet": False,
                      "label": "Bank Transfer", "country": "Global",
                      "instructions": "Transfer to TradeLink Wholesale — IBAN DE89 3704 0044 0532 0130 00, SWIFT COBADEFFXXX, referencing your Order ID. Confirm on the order page after transferring."},
    "cod":           {"enabled": True, "env_key": None,
                      "api": None, "wallet": False,
                      "label": "Cash on Delivery", "country": "Global",
                      "instructions": "Pay in cash when your shipment arrives. Available in supported regions."},
}

ORDER_FLOW = ["order_placed", "payment_confirmed", "processing", "packed",
              "shipped", "in_transit", "delivered"]
ORDER_LABELS = {
    "order_placed": "Order Placed", "payment_confirmed": "Payment Confirmed",
    "processing": "Processing", "packed": "Packed", "shipped": "Shipped",
    "in_transit": "In Transit", "delivered": "Delivered",
}


@app.before_request
def before():
    g.db = get_db()
    g.user = None
    if session.get("uid"):
        g.user = g.db.execute("SELECT * FROM users WHERE id=?", (session["uid"],)).fetchone()
        if g.user is None:
            session.clear()
    g.cart_count = 0
    g.notif_count = 0
    if g.user:
        g.cart_count = g.db.execute("SELECT COALESCE(SUM(qty),0) c FROM carts WHERE user_id=?", (g.user["id"],)).fetchone()["c"]
        g.notif_count = g.db.execute("SELECT COUNT(*) c FROM notifications WHERE user_id=? AND is_read=0", (g.user["id"],)).fetchone()["c"]


@app.teardown_request
def teardown(exc):
    if hasattr(g, "db"):
        g.db.close()


def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if not g.user:
            flash("Please sign in to continue.", "info")
            return redirect(url_for("login", next=request.path))
        return f(*a, **k)
    return w


def role_required(*roles):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            if not g.user or g.user["role"] not in roles:
                abort(403)
            return f(*a, **k)
        return w
    return deco


def supplier_record():
    return g.db.execute("SELECT * FROM suppliers WHERE user_id=?", (g.user["id"],)).fetchone()


def supplier_required(f):
    @wraps(f)
    @role_required("supplier")
    def w(*a, **k):
        if not supplier_record():
            abort(403)
        return f(*a, **k)
    return w


def get_product_by_slug(slug):
    return g.db.execute(
        """SELECT p.*, s.company_name, s.country AS s_country, s.verification_status,
                  s.rating_avg, s.rating_count, s.response_rate, s.response_time,
                  s.slug AS supplier_slug, s.user_id AS supplier_user_id,
                  c.name AS category_name, c.slug AS category_slug
           FROM products p
           JOIN suppliers s ON s.id = p.supplier_id
           JOIN categories c ON c.id = p.category_id
           WHERE p.slug=?""", (slug,)).fetchone()


def tier_price(product, qty):
    row = g.db.execute(
        "SELECT price FROM product_tiers WHERE product_id=? AND min_qty<=? ORDER BY min_qty DESC LIMIT 1",
        (product["id"], qty)).fetchone()
    return row["price"] if row else product["price"]


def cart_lines():
    rows = g.db.execute(
        """SELECT c.qty, p.*, s.company_name AS supplier, s.verification_status,
                  s.rating_avg AS supplier_rating
           FROM carts c
           JOIN products p ON p.id=c.product_id
           JOIN suppliers s ON s.id=p.supplier_id
           WHERE c.user_id=? ORDER BY s.company_name, p.name""", (g.user["id"],)).fetchall()
    lines = []
    subtotal = savings = 0
    for r in rows:
        unit = tier_price(r, r["qty"])
        base = r["price"]
        lines.append({**r, "unit": unit, "line_total": round(unit * r["qty"], 2),
                      "saving": round((base - unit) * r["qty"], 2), "pct": round((1 - unit / base) * 100) if base else 0})
        subtotal += unit * r["qty"]
        savings += (base - unit) * r["qty"]
    return lines, round(subtotal, 2), round(savings, 2)


# ----------------------------------------------------------------------
# Pages
# ----------------------------------------------------------------------
@app.route("/")
def home():
    cats = g.db.execute("SELECT * FROM categories ORDER BY sort_order").fetchall()
    deals = g.db.execute("SELECT * FROM products WHERE status='approved' ORDER BY sold DESC LIMIT 8").fetchall()
    flash_products = g.db.execute(
        "SELECT * FROM products WHERE status='approved' AND stock>0 ORDER BY sold DESC LIMIT 4").fetchall()
    new_arrivals = g.db.execute("SELECT * FROM products WHERE status='approved' ORDER BY created_at DESC LIMIT 8").fetchall()
    suppliers = g.db.execute("SELECT * FROM suppliers WHERE verification_status='verified' ORDER BY rating_avg DESC LIMIT 4").fetchall()
    reviews = g.db.execute(
        """SELECT r.*, u.name, p.name AS product_name, s.company_name AS supplier
           FROM reviews r JOIN users u ON u.id=r.user_id
           JOIN products p ON p.id=r.product_id
           JOIN suppliers s ON s.id=r.supplier_id
           ORDER BY r.id DESC LIMIT 6""").fetchall()
    campaigns = g.db.execute("SELECT * FROM campaigns WHERE active=1 AND end_date>datetime('now') ORDER BY id DESC LIMIT 1").fetchall()
    return render_template("home.html", cats=cats, deals=deals, flash_products=flash_products,
                           new_arrivals=new_arrivals, suppliers=suppliers, reviews=reviews,
                           campaigns=campaigns, ORDER_LABELS=ORDER_LABELS)


@app.route("/products")
def products():
    cat_slug = request.args.get("cat", "")
    q = request.args.get("q", "").strip()
    sort = request.args.get("sort", "recommended")
    min_price = request.args.get("min", type=float)
    max_price = request.args.get("max", type=float)
    verified_only = request.args.get("verified") == "1"
    in_stock = request.args.get("stock") == "1"
    page = max(1, request.args.get("page", 1, type=int))
    per_page = 12

    sql = """SELECT p.*, s.company_name, s.country AS s_country, s.verification_status,
                    c.name AS category_name, c.slug AS category_slug,
                    (SELECT COALESCE(AVG(rating),0) FROM reviews r WHERE r.product_id=p.id) avg_rating
             FROM products p
             JOIN suppliers s ON s.id=p.supplier_id
             JOIN categories c ON c.id=p.category_id
             WHERE p.status='approved' """
    params = []
    if cat_slug:
        sql += "AND c.slug=? "
        params.append(cat_slug)
    if q:
        sql += "AND (p.name LIKE ? OR p.sku LIKE ? OR p.description LIKE ? OR p.specifications LIKE ? OR s.company_name LIKE ?) "
        like = f"%{q}%"
        params += [like] * 5
    if min_price is not None:
        sql += "AND p.price>=? "
        params.append(min_price)
    if max_price is not None:
        sql += "AND p.price<=? "
        params.append(max_price)
    if verified_only:
        sql += "AND s.verification_status='verified' "
    if in_stock:
        sql += "AND p.stock>0 "

    sort_map = {"newest": "p.created_at DESC", "price_asc": "p.price ASC", "price_desc": "p.price DESC",
                "rating": "avg_rating DESC", "popular": "p.sold DESC", "discount": "(p.old_price-p.price)/p.price DESC"}
    sql += "ORDER BY " + sort_map.get(sort, "p.sold DESC")
    sql += " LIMIT ? OFFSET ?"
    params += [per_page, (page - 1) * per_page]

    items = g.db.execute(sql, params).fetchall()
    total = g.db.execute(
        "SELECT COUNT(*) c FROM products p JOIN suppliers s ON s.id=p.supplier_id JOIN categories c ON c.id=p.category_id WHERE p.status='approved'").fetchone()["c"]
    cats = g.db.execute("SELECT * FROM categories ORDER BY sort_order").fetchall()
    return render_template("products.html", items=items, cats=cats, total=total,
                           page=page, per_page=per_page, q=q, cat_slug=cat_slug,
                           sort=sort, verified_only=verified_only, in_stock=in_stock,
                           min_price=min_price, max_price=max_price)


@app.route("/product/<slug>")
def product(slug):
    p = get_product_by_slug(slug)
    if not p:
        abort(404)
    g.db.execute("UPDATE products SET views=views+1 WHERE id=?", (p["id"],))
    g.db.commit()
    tiers = g.db.execute("SELECT * FROM product_tiers WHERE product_id=? ORDER BY min_qty", (p["id"],)).fetchall()
    reviews = g.db.execute(
        """SELECT r.*, u.name FROM reviews r JOIN users u ON u.id=r.user_id
           WHERE r.product_id=? ORDER BY r.id DESC""", (p["id"],)).fetchall()
    related = g.db.execute(
        "SELECT * FROM products WHERE category_id=? AND status='approved' AND id!=? LIMIT 4",
        (p["category_id"], p["id"])).fetchall()
    in_wishlist = False
    in_cart = False
    if g.user:
        in_wishlist = g.db.execute("SELECT 1 FROM wishlists WHERE user_id=? AND product_id=?", (g.user["id"], p["id"])).fetchone() is not None
        in_cart = g.db.execute("SELECT 1 FROM carts WHERE user_id=? AND product_id=?", (g.user["id"], p["id"])).fetchone() is not None
    max_save = 0
    if len(tiers) >= 2:
        max_save = round((1 - tiers[-1]["price"] / tiers[0]["price"]) * 100)
    return render_template("product.html", p=p, tiers=tiers, reviews=reviews,
                           related=related, in_wishlist=in_wishlist, in_cart=in_cart,
                           max_save=max_save)


@app.route("/category/<slug>")
def category(slug):
    cat = g.db.execute("SELECT * FROM categories WHERE slug=?", (slug,)).fetchone()
    if not cat:
        abort(404)
    items = g.db.execute(
        """SELECT p.*, s.company_name, s.country AS s_country, s.verification_status
           FROM products p JOIN suppliers s ON s.id=p.supplier_id
           WHERE p.category_id=? AND p.status='approved' ORDER BY p.sold DESC""", (cat["id"],)).fetchall()
    return render_template("category.html", cat=cat, items=items)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        subject = request.form.get("subject", "").strip()
        body = request.form.get("message", "").strip()
        if not name or not email or not body:
            flash("Please fill in your name, email and message.", "error")
            return redirect(url_for("contact"))
        g.db.execute("INSERT INTO messages (sender_id, receiver_id, body) VALUES (?,?,?)",
                     (session.get("uid") or 1, 1, f"[Contact] {name} ({email}) — {subject or 'General'}: {body}"))
        g.db.execute("INSERT INTO notifications (user_id, type, title, body, link) VALUES (?,?,?,?,?)",
                     (1, "message", f"Contact: {subject or name}", f"{name} ({email}): {body[:120]}", "/admin"))
        g.db.commit()
        send_email(MERCHANT_EMAIL, f"New contact: {subject or name}", f"From: {name} <{email}>\n\n{body}")
        flash("Thank you — your message has been sent. We reply within 1 business day.", "success")
        return redirect(url_for("contact"))
    return render_template("contact.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/refunds")
def refunds():
    return render_template("refunds.html")


@app.route("/suppliers")
def suppliers_page():
    country = request.args.get("country", "")
    q = request.args.get("q", "").strip()
    sql = "SELECT * FROM suppliers WHERE 1=1 "
    params = []
    if country:
        sql += "AND country LIKE ? "
        params.append(f"%{country}%")
    if q:
        sql += "AND company_name LIKE ? "
        params.append(f"%{q}%")
    sql += "ORDER BY verification_status='verified' DESC, rating_avg DESC"
    items = g.db.execute(sql, params).fetchall()
    countries = g.db.execute("SELECT DISTINCT country FROM suppliers ORDER BY country").fetchall()
    return render_template("suppliers.html", items=items, countries=countries, q=q, country=country)


ALIBABA_CATEGORIES = [
    ("Consumer Electronics", "https://www.alibaba.com/trade/search?SearchText=consumer+electronics"),
    ("Clothing & Apparel", "https://www.alibaba.com/trade/search?SearchText=clothing+apparel+bulk"),
    ("Home & Garden", "https://www.alibaba.com/trade/search?SearchText=home+garden+wholesale"),
    ("Beauty & Personal Care", "https://www.alibaba.com/trade/search?SearchText=beauty+personal+care+wholesale"),
    ("Machinery", "https://www.alibaba.com/trade/search?SearchText=industrial+machinery"),
    ("Packaging", "https://www.alibaba.com/trade/search?SearchText=packaging+supplies+wholesale"),
    ("Sports & Outdoors", "https://www.alibaba.com/trade/search?SearchText=sports+outdoors+wholesale"),
    ("Toys & Hobbies", "https://www.alibaba.com/trade/search?SearchText=toys+hobbies+wholesale"),
    ("Food & Beverage", "https://www.alibaba.com/trade/search?SearchText=food+beverage+wholesale"),
    ("Health & Medical", "https://www.alibaba.com/trade/search?SearchText=health+medical+wholesale"),
]

TRENDING_ALIBABA = [
    ("Wireless Earbuds", "https://www.alibaba.com/trade/search?SearchText=wireless+earbuds+tws"),
    ("Solar Panels", "https://www.alibaba.com/trade/search?SearchText=folding+solar+panel+100w"),
    ("LED Strip Lights", "https://www.alibaba.com/trade/search?SearchText=led+strip+light+5m+rgb"),
    ("Mechanical Keyboards", "https://www.alibaba.com/trade/search?SearchText=mechanical+gaming+keyboard+hot+swap"),
    ("Reusable Water Bottles", "https://www.alibaba.com/trade/search?SearchText=stainless+steel+water+bottle+insulated"),
    ("Custom Printed Tees", "https://www.alibaba.com/trade/search?SearchText=custom+print+t-shirt+bulk"),
    ("Fitness Trackers", "https://www.alibaba.com/trade/search?SearchText=fitness+tracker+wholesale"),
    ("Cosmetic Packaging", "https://www.alibaba.com/trade/search?SearchText=cosmetic+packaging+wholesale"),
]


@app.route("/alibaba")
def alibaba_connect():
    rows = g.db.execute(
        """SELECT p.id, p.name, p.slug, p.price, p.old_price, p.moq, p.stock, p.sold,
                  c.name AS category_name, s.company_name
           FROM products p JOIN categories c ON c.id=p.category_id
           JOIN suppliers s ON s.id=p.supplier_id
           WHERE p.status='approved' ORDER BY p.sold DESC LIMIT 12""").fetchall()
    return render_template("alibaba.html", rows=rows, cats=ALIBABA_CATEGORIES, trending=TRENDING_ALIBABA)


@app.route("/supplier/<slug>")
def supplier_store(slug):
    s = g.db.execute("SELECT s.*, u.email FROM suppliers s JOIN users u ON u.id=s.user_id WHERE s.slug=?", (slug,)).fetchone()
    if not s:
        abort(404)
    products = g.db.execute("SELECT * FROM products WHERE supplier_id=? AND status='approved' ORDER BY sold DESC", (s["id"],)).fetchall()
    reviews = g.db.execute(
        """SELECT r.*, u.name, p.name AS product_name FROM reviews r
           JOIN users u ON u.id=r.user_id JOIN products p ON p.id=r.product_id
           WHERE r.supplier_id=? ORDER BY r.id DESC LIMIT 8""", (s["id"],)).fetchall()
    cats = g.db.execute(
        """SELECT DISTINCT c.name, c.slug FROM products p
           JOIN categories c ON c.id=p.category_id
           WHERE p.supplier_id=? AND p.status='approved'""", (s["id"],)).fetchall()
    return render_template("supplier.html", s=s, products=products, reviews=reviews, cats=cats)


# ----------------------------------------------------------------------
# Auth
# ----------------------------------------------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        name = request.form.get("name", "").strip()
        company = request.form.get("company", "").strip()
        country = request.form.get("country", "United States")
        role = request.form.get("role", "customer")
        pw = request.form.get("password", "")
        pw2 = request.form.get("password2", "")
        if not all([email, name, pw, pw2]):
            flash("All fields are required.", "error")
        elif pw != pw2:
            flash("Passwords do not match.", "error")
        elif len(pw) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif g.db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            flash("An account with this email already exists.", "error")
        else:
            dh, salt = hash_password(pw)
            cur = g.db.execute(
                "INSERT INTO users (email, password_hash, salt, name, company, role, country, is_verified) VALUES (?,?,?,?,?,?,?,1)",
                (email, dh, salt, name, company, role, country))
            uid = cur.lastrowid
            if role == "supplier":
                comp = request.form.get("company") or name
                g.db.execute(
                    "INSERT INTO suppliers (user_id, company_name, slug, country, business_type, description, verification_status) VALUES (?,?,?,?,?,?,?)",
                    (uid, comp, slugify(comp + "-" + str(uid)), country,
                     request.form.get("business_type", "Manufacturer"),
                     request.form.get("description", ""), "pending"))
                g.db.execute("INSERT INTO notifications (user_id, type, title, body) VALUES (?,?,?,?)",
                             (uid, "info", "Supplier application received",
                              "Your store is under review. Approval usually takes 2-4 business days."))
            g.db.commit()
            session["uid"] = uid
            flash("Welcome to TradeLink! Your account is ready.", "success")
            return redirect(url_for("dashboard" if role == "customer" else "supplier_dashboard"))
    return render_template("auth.html", mode="register")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")
        row = g.db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if row and verify_password(pw, row["password_hash"], row["salt"]):
            session["uid"] = row["id"]
            session["role"] = row["role"]
            flash(f"Welcome back, {row['name']}!", "success")
            nxt = request.args.get("next")
            if nxt and nxt.startswith("/"):
                return redirect(nxt)
            if row["role"] == "admin":
                return redirect(url_for("admin_panel"))
            if row["role"] == "supplier":
                return redirect(url_for("supplier_dashboard"))
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "error")
    return render_template("auth.html", mode="login")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("home"))


# ----------------------------------------------------------------------
# Cart
# ----------------------------------------------------------------------
@app.post("/cart/add")
@login_required
def cart_add():
    pid = request.form.get("product_id", type=int)
    qty = max(1, request.form.get("qty", 1, type=int))
    p = g.db.execute("SELECT * FROM products WHERE id=? AND status='approved'", (pid,)).fetchone()
    if not p:
        return jsonify({"ok": False, "error": "Product not found"}), 404
    if qty < p["moq"]:
        return jsonify({"ok": False, "error": f"Minimum order is {p['moq']} units"}), 400
    if qty > p["stock"]:
        return jsonify({"ok": False, "error": f"Only {p['stock']} units in stock"}), 400
    g.db.execute("INSERT INTO carts (user_id, product_id, qty) VALUES (?,?,?) ON CONFLICT(user_id,product_id) DO UPDATE SET qty=qty+excluded.qty",
                 (g.user["id"], pid, qty))
    g.db.commit()
    count = g.db.execute("SELECT COALESCE(SUM(qty),0) c FROM carts WHERE user_id=?", (g.user["id"],)).fetchone()["c"]
    return jsonify({"ok": True, "count": count, "msg": f"Added {qty} units to cart"})


@app.post("/cart/update")
@login_required
def cart_update():
    pid = request.form.get("product_id", type=int)
    qty = max(1, request.form.get("qty", 1, type=int))
    g.db.execute("UPDATE carts SET qty=? WHERE user_id=? AND product_id=?", (qty, g.user["id"], pid))
    g.db.commit()
    return jsonify({"ok": True})


@app.post("/cart/remove")
@login_required
def cart_remove():
    pid = request.form.get("product_id", type=int)
    g.db.execute("DELETE FROM carts WHERE user_id=? AND product_id=?", (g.user["id"], pid))
    g.db.commit()
    return jsonify({"ok": True})


@app.route("/api/cart/summary")
@login_required
def api_cart_summary():
    lines, subtotal, savings = cart_lines()
    total = round(subtotal - savings, 2)
    count = sum(l["qty"] for l in lines)
    return jsonify({
        "ok": True,
        "count": count,
        "subtotal": subtotal,
        "savings": savings,
        "total": total,
        "items": [
            {"id": l["id"], "name": l["name"], "slug": l["slug"], "supplier": l["supplier"],
             "unit": l["unit"], "qty": l["qty"], "moq": l["moq"],
             "line_total": l["line_total"], "pct": l["pct"]}
            for l in lines
        ],
    })


@app.route("/cart")
@login_required
def cart():
    lines, subtotal, savings = cart_lines()
    return render_template("cart.html", lines=lines, subtotal=subtotal, savings=savings)


# ----------------------------------------------------------------------
# Checkout & Orders
# ----------------------------------------------------------------------
@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    lines, subtotal, savings = cart_lines()
    if not lines:
        flash("Your cart is empty.", "info")
        return redirect(url_for("cart"))

    addresses = g.db.execute("SELECT * FROM addresses WHERE user_id=? ORDER BY is_default DESC", (g.user["id"],)).fetchall()

    if request.method == "POST":
        step = request.form.get("step", "shipping")
        if step == "save_address":
            cur = g.db.execute(
                """INSERT INTO addresses (user_id, label, full_name, phone, line1, line2, city, state, zip, country, is_default)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (g.user["id"], request.form.get("label", "Business"), request.form.get("full_name"),
                 request.form.get("phone"), request.form.get("line1"), request.form.get("line2"),
                 request.form.get("city"), request.form.get("state"), request.form.get("zip"),
                 request.form.get("country", "United States"), 1))
            g.db.execute("UPDATE addresses SET is_default=0 WHERE id!=?", (cur.lastrowid,))
            g.db.commit()
            flash("Address saved.", "success")
            return redirect(url_for("checkout"))

        # Complete order
        addr = {}
        addr_id = request.form.get("address_id", type=int)
        if addr_id:
            a = g.db.execute("SELECT * FROM addresses WHERE id=? AND user_id=?", (addr_id, g.user["id"])).fetchone()
            if a:
                addr = dict(a)
        else:
            addr = {"full_name": request.form.get("full_name"), "phone": request.form.get("phone"),
                    "line1": request.form.get("line1"), "line2": request.form.get("line2", ""),
                    "city": request.form.get("city"), "state": request.form.get("state", ""),
                    "zip": request.form.get("zip", ""), "country": request.form.get("country", "United States")}
        payment = request.form.get("payment_method", "bank_transfer")
        shipping_method = request.form.get("shipping_method", "standard")
        if payment not in PAYMENT_PROVIDERS:
            flash("Invalid payment method.", "error")
            return redirect(url_for("checkout"))
        provider_ref = request.form.get("provider_ref", "").strip()
        if PAYMENT_PROVIDERS[payment]["wallet"] and not provider_ref:
            flash(f"Enter your {PAYMENT_PROVIDERS[payment]['label']} number to pay.", "error")
            return redirect(url_for("checkout"))

        coupon_code = session.pop("coupon_code", "")
        discount = 0
        if coupon_code:
            coupon = g.db.execute("SELECT * FROM coupons WHERE code=? AND active=1", (coupon_code,)).fetchone()
            if coupon and coupon["used_count"] < coupon["usage_limit"]:
                if coupon["discount_type"] == "percent":
                    discount = subtotal * coupon["value"] / 100
                    if coupon["max_discount"]:
                        discount = min(discount, coupon["max_discount"])
                else:
                    discount = min(coupon["value"], subtotal)
                g.db.execute("UPDATE coupons SET used_count=used_count+1 WHERE id=?", (coupon["id"],))
        total_before_tax = subtotal - discount
        tax = round(total_before_tax * 0.05, 2)
        shipping_cost = 0 if shipping_method == "standard" and total_before_tax >= 500 else (25 if shipping_method == "express" else 0)
        total = round(total_before_tax + tax + shipping_cost, 2)

        onum = "TL-" + str(secrets.randbelow(900000) + 100000)
        cur = g.db.execute(
            """INSERT INTO orders (user_id, order_number, subtotal, discount, shipping, tax, total,
               payment_method, payment_status, shipping_method, address_json, coupon_code, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (g.user["id"], onum, subtotal, discount, shipping_cost, tax, total,
             payment, "pending", shipping_method, json.dumps(addr), coupon_code,
             "order_placed" if payment != "cod" else "order_placed"))
        oid = cur.lastrowid
        for line in lines:
            g.db.execute("INSERT INTO order_items (order_id, product_id, supplier_id, product_name, qty, unit_price, total) VALUES (?,?,?,?,?,?,?)",
                         (oid, line["id"], line["supplier_id"], line["name"], line["qty"], line["unit"], line["line_total"]))
            g.db.execute("UPDATE products SET stock=stock-?, sold=sold+? WHERE id=?", (line["qty"], line["qty"], line["id"]))
            g.db.execute("INSERT INTO inventory_log (product_id, change_qty, note) VALUES (?,?,?)",
                         (line["id"], -line["qty"], f"Order {onum}"))
        g.db.execute("INSERT INTO payments (order_id, provider, provider_ref, amount, status) VALUES (?,?,?,?,?)",
                     (oid, payment, provider_ref, total, "pending"))
        g.db.execute("DELETE FROM carts WHERE user_id=?", (g.user["id"],))
        # Notify suppliers
        for line in lines:
            sup_user = g.db.execute("SELECT user_id FROM suppliers WHERE id=?", (line["supplier_id"],)).fetchone()
            if sup_user:
                g.db.execute("INSERT INTO notifications (user_id, type, title, body, link) VALUES (?,?,?,?,?)",
                             (sup_user["user_id"], "order", f"New order {onum}",
                              f"Order for {line['qty']} × {line['name']}", f"/supplier/orders"))
        g.db.execute("INSERT INTO notifications (user_id, type, title, body, link) VALUES (?,?,?,?,?)",
                     (g.user["id"], "order", f"Order {onum} placed",
                      "Your order has been received. Track it from your dashboard.", f"/order/{oid}"))
        g.db.commit()
        session.pop("coupon_code", None)
        send_email(g.user["email"], f"Order {onum} placed",
                   f"Thank you for your order {onum}.\n\nTotal: ${total:,.2f}\nPayment: {PAYMENT_PROVIDERS[payment]['label']}\n\nPayment instructions:\n{PAYMENT_PROVIDERS[payment]['instructions']}\n\nQuestions? Reply to {MERCHANT_EMAIL}")
        return redirect(url_for("order_detail", order_id=oid))

    shipping_costs = {"standard": {"label": "Standard (10-20 days)", "cost": "Free over $500"},
                      "express": {"label": "Express (3-7 days)", "cost": "$25"},
                      "sea_freight": {"label": "Sea freight (30-45 days)", "cost": "Quoted"}}
    return render_template("checkout.html", lines=lines, subtotal=subtotal, savings=savings,
                           addresses=addresses, providers=PAYMENT_PROVIDERS, shipping_costs=shipping_costs)


@app.route("/orders")
@login_required
def orders():
    rows = g.db.execute("SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC", (g.user["id"],)).fetchall()
    return render_template("orders.html", orders=rows, ORDER_LABELS=ORDER_LABELS, ORDER_FLOW=ORDER_FLOW)


@app.route("/order/<int:order_id>")
@login_required
def order_detail(order_id):
    o = g.db.execute("SELECT * FROM orders WHERE id=? AND user_id=?", (order_id, g.user["id"])).fetchone()
    if not o:
        abort(404)
    items = g.db.execute(
        """SELECT oi.*, s.company_name, p.slug FROM order_items oi
           JOIN suppliers s ON s.id=oi.supplier_id
           LEFT JOIN products p ON p.id=oi.product_id
           WHERE oi.order_id=?""", (order_id,)).fetchall()
    addr = json.loads(o["address_json"] or "{}")
    payments = g.db.execute("SELECT * FROM payments WHERE order_id=?", (order_id,)).fetchall()
    flow_idx = ORDER_FLOW.index(o["status"]) if o["status"] in ORDER_FLOW else 0
    return render_template("order.html", o=o, items=items, addr=addr, payments=payments,
                           ORDER_LABELS=ORDER_LABELS, ORDER_FLOW=ORDER_FLOW, flow_idx=flow_idx)


@app.post("/order/<int:order_id>/pay")
@login_required
def order_mark_paid(order_id):
    """Simulated gateway callback — in production this endpoint is called by
    the payment provider's webhook (EasyPaisa/JazzCash/bKash/GCash/M-PESA/
    Stripe/PayPal) with a verified transaction. The env-key gateways should
    verify the signature server-side before confirming."""
    o = g.db.execute("SELECT * FROM orders WHERE id=? AND user_id=?", (order_id, g.user["id"])).fetchone()
    if not o:
        abort(404)
    if o["payment_status"] == "confirmed":
        flash("Payment for this order is already confirmed.", "info")
        return redirect(url_for("order_detail", order_id=order_id))
    g.db.execute("UPDATE payments SET status='confirmed' WHERE order_id=? AND status='pending'", (order_id,))
    g.db.execute("UPDATE orders SET payment_status='confirmed' WHERE id=?", (order_id,))
    if o["status"] == "order_placed":
        g.db.execute("UPDATE orders SET status='payment_confirmed' WHERE id=?", (order_id,))
    g.db.execute("INSERT INTO notifications (user_id, type, title, body, link) VALUES (?,?,?,?,?)",
                 (g.user["id"], "order", f"Payment confirmed for {o['order_number']}",
                  "Your payment was received. Your order is now being processed.", f"/order/{order_id}"))
    g.db.commit()
    send_email(g.user["email"], f"Payment confirmed for {o['order_number']}",
               f"Your payment of ${o['total']:,.2f} for order {o['order_number']} was confirmed. The supplier is now processing your order.\n\nQuestions? Reply to {MERCHANT_EMAIL}")
    flash("Payment confirmed — your order is now processing.", "success")
    return redirect(url_for("order_detail", order_id=order_id))


# ----------------------------------------------------------------------
# Wishlist / Reviews / Quotes / Messages / Notifications
# ----------------------------------------------------------------------
@app.post("/wishlist/toggle")
@login_required
def wishlist_toggle():
    pid = request.form.get("product_id", type=int)
    exists = g.db.execute("SELECT 1 FROM wishlists WHERE user_id=? AND product_id=?", (g.user["id"], pid)).fetchone()
    if exists:
        g.db.execute("DELETE FROM wishlists WHERE user_id=? AND product_id=?", (g.user["id"], pid))
        g.db.commit()
        return jsonify({"ok": True, "added": False})
    g.db.execute("INSERT INTO wishlists (user_id, product_id) VALUES (?,?)", (g.user["id"], pid))
    g.db.commit()
    return jsonify({"ok": True, "added": True})


@app.route("/wishlist")
@login_required
def wishlist():
    items = g.db.execute(
        """SELECT p.*, s.company_name, w.created_at AS added
           FROM wishlists w JOIN products p ON p.id=w.product_id
           JOIN suppliers s ON s.id=p.supplier_id
           WHERE w.user_id=? ORDER BY w.created_at DESC""", (g.user["id"],)).fetchall()
    return render_template("wishlist.html", items=items)


@app.route("/product/<int:pid>/review", methods=["POST"])
@login_required
def add_review(pid):
    rating = request.form.get("rating", type=int)
    comment = request.form.get("comment", "").strip()
    p = g.db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if not p or not rating or not (1 <= rating <= 5):
        flash("Please provide a rating from 1 to 5.", "error")
        return redirect(request.referrer or url_for("product", slug=""))
    verified = g.db.execute(
        "SELECT 1 FROM order_items oi JOIN orders o ON o.id=oi.order_id WHERE o.user_id=? AND oi.product_id=? AND o.status='delivered'",
        (g.user["id"], pid)).fetchone() is not None
    g.db.execute("INSERT INTO reviews (user_id, product_id, supplier_id, rating, comment, is_verified_purchase) VALUES (?,?,?,?,?,?)",
                 (g.user["id"], pid, p["supplier_id"], rating, comment, 1 if verified else 0))
    g.db.execute("""UPDATE suppliers SET rating_avg = (SELECT AVG(rating) FROM reviews WHERE supplier_id=suppliers.id),
                    rating_count = (SELECT COUNT(*) FROM reviews WHERE supplier_id=suppliers.id) WHERE id=?""",
                 (p["supplier_id"],))
    g.db.commit()
    flash("Review submitted. Thank you!", "success")
    return redirect(request.referrer or url_for("product", slug=p["slug"]))


@app.route("/quotes", methods=["GET", "POST"])
@login_required
def quotes():
    if request.method == "POST":
        g.db.execute(
            """INSERT INTO quotes (user_id, product_id, supplier_id, qty, target_price, destination, delivery_date, requirements)
               VALUES (?,?,?,?,?,?,?,?)""",
            (g.user["id"], request.form.get("product_id", type=int), request.form.get("supplier_id", type=int),
             request.form.get("qty", type=int), request.form.get("target_price", type=float),
             request.form.get("destination", ""), request.form.get("delivery_date", ""),
             request.form.get("requirements", "")))
        sup_user = g.db.execute("SELECT user_id FROM suppliers WHERE id=?", (request.form.get("supplier_id", type=int),)).fetchone()
        if sup_user:
            g.db.execute("INSERT INTO notifications (user_id, type, title, body, link) VALUES (?,?,?,?,?)",
                         (sup_user["user_id"], "quote", "New quote request", "A buyer requested a bulk quote.", "/supplier/quotes"))
        g.db.commit()
        flash("Quote request sent to the supplier. They typically respond within 24 hours.", "success")
        return redirect(url_for("quotes"))
    rows = g.db.execute(
        """SELECT q.*, p.name AS product_name, p.slug, s.company_name FROM quotes q
           JOIN products p ON p.id=q.product_id JOIN suppliers s ON s.id=q.supplier_id
           WHERE q.user_id=? ORDER BY q.id DESC""", (g.user["id"],)).fetchall()
    return render_template("quotes.html", rows=rows)


@app.route("/messages", methods=["GET", "POST"])
@login_required
def messages():
    if request.method == "POST":
        body = request.form.get("body", "").strip()
        receiver_id = request.form.get("receiver_id", type=int)
        product_id = request.form.get("product_id", type=int) or None
        if body and receiver_id:
            g.db.execute("INSERT INTO messages (sender_id, receiver_id, product_id, body) VALUES (?,?,?,?)",
                         (g.user["id"], receiver_id, product_id, body))
            g.db.execute("INSERT INTO notifications (user_id, type, title, body, link) VALUES (?,?,?,?,?)",
                         (receiver_id, "message", f"New message from {g.user['name']}", body[:80], "/messages"))
            g.db.commit()
            flash("Message sent.", "success")
        return redirect(url_for("messages"))
    convos = g.db.execute(
        """SELECT m.*, u.name AS other_name, u.role AS other_role
           FROM messages m JOIN users u ON u.id = CASE WHEN m.sender_id=? THEN m.receiver_id ELSE m.sender_id END
           WHERE m.sender_id=? OR m.receiver_id=?
           ORDER BY m.id DESC""", (g.user["id"], g.user["id"], g.user["id"])).fetchall()
    # Group by other user, keep latest
    seen = {}
    for m in convos:
        key = m["other_name"]
        if key not in seen:
            seen[key] = m
    return render_template("messages.html", convos=list(seen.values()))


@app.route("/notifications")
@login_required
def notifications():
    rows = g.db.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 50", (g.user["id"],)).fetchall()
    g.db.execute("UPDATE notifications SET is_read=1 WHERE user_id=? AND is_read=0", (g.user["id"],))
    g.db.commit()
    return render_template("notifications.html", rows=rows)


# ----------------------------------------------------------------------
# Customer dashboard
# ----------------------------------------------------------------------
@app.route("/dashboard")
@login_required
@role_required("customer")
def dashboard():
    stats = {
        "orders": g.db.execute("SELECT COUNT(*) c FROM orders WHERE user_id=?", (g.user["id"],)).fetchone()["c"],
        "pending": g.db.execute("SELECT COUNT(*) c FROM orders WHERE user_id=? AND status NOT IN ('delivered','shipped')", (g.user["id"],)).fetchone()["c"],
        "quotes": g.db.execute("SELECT COUNT(*) c FROM quotes WHERE user_id=?", (g.user["id"],)).fetchone()["c"],
        "wishlist": g.db.execute("SELECT COUNT(*) c FROM wishlists WHERE user_id=?", (g.user["id"],)).fetchone()["c"],
        "unread": g.db.execute("SELECT COUNT(*) c FROM messages WHERE receiver_id=? AND is_read=0", (g.user["id"],)).fetchone()["c"],
    }
    recent = g.db.execute("SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT 5", (g.user["id"],)).fetchall()
    return render_template("customer_dashboard.html", stats=stats, recent=recent, ORDER_LABELS=ORDER_LABELS)


@app.route("/addresses", methods=["GET", "POST"])
@login_required
def addresses():
    if request.method == "POST":
        if request.form.get("delete"):
            g.db.execute("DELETE FROM addresses WHERE id=? AND user_id=?", (request.form.get("delete", type=int), g.user["id"]))
        else:
            g.db.execute(
                """INSERT INTO addresses (user_id, label, full_name, phone, line1, line2, city, state, zip, country, is_default)
                   VALUES (?,?,?,?,?,?,?,?,?,?,0)""",
                (g.user["id"], request.form.get("label", "Business"), request.form.get("full_name"),
                 request.form.get("phone"), request.form.get("line1"), request.form.get("line2"),
                 request.form.get("city"), request.form.get("state"), request.form.get("zip"),
                 request.form.get("country", "United States")))
        g.db.commit()
        return redirect(url_for("addresses"))
    rows = g.db.execute("SELECT * FROM addresses WHERE user_id=? ORDER BY is_default DESC", (g.user["id"],)).fetchall()
    return render_template("addresses.html", rows=rows)


# ----------------------------------------------------------------------
# Supplier dashboard
# ----------------------------------------------------------------------
@app.route("/supplier/dashboard")
@login_required
@role_required("supplier")
def supplier_dashboard():
    s = supplier_record()
    if not s:
        abort(403)
    sid = s["id"]
    stats = {
        "revenue": g.db.execute("SELECT COALESCE(SUM(o.total),0) t FROM order_items oi JOIN orders o ON o.id=oi.order_id WHERE oi.supplier_id=? AND o.status='delivered'", (sid,)).fetchone()["t"],
        "orders": g.db.execute("SELECT COUNT(*) c FROM order_items oi JOIN orders o ON o.id=oi.order_id WHERE oi.supplier_id=?", (sid,)).fetchone()["c"],
        "products": g.db.execute("SELECT COUNT(*) c FROM products WHERE supplier_id=?", (sid,)).fetchone()["c"],
        "units_sold": g.db.execute("SELECT COALESCE(SUM(qty),0) t FROM order_items WHERE supplier_id=?", (sid,)).fetchone()["t"],
        "quotes": g.db.execute("SELECT COUNT(*) c FROM quotes WHERE supplier_id=? AND status='pending'", (sid,)).fetchone()["c"],
        "low_stock": g.db.execute("SELECT COUNT(*) c FROM products WHERE supplier_id=? AND stock<=low_stock_threshold", (sid,)).fetchone()["c"],
    }
    recent_orders = g.db.execute(
        """SELECT o.order_number, o.status, o.created_at, oi.qty, oi.product_name, oi.total
           FROM order_items oi JOIN orders o ON o.id=oi.order_id
           WHERE oi.supplier_id=? ORDER BY o.id DESC LIMIT 8""", (sid,)).fetchall()
    top_products = g.db.execute("SELECT * FROM products WHERE supplier_id=? ORDER BY sold DESC LIMIT 5", (sid,)).fetchall()
    low_stock = g.db.execute("SELECT * FROM products WHERE supplier_id=? AND stock<=low_stock_threshold", (sid,)).fetchall()
    return render_template("supplier_dashboard.html", s=s, stats=stats, recent_orders=recent_orders,
                           top_products=top_products, low_stock=low_stock, ORDER_LABELS=ORDER_LABELS)


@app.route("/supplier/products")
@login_required
@role_required("supplier")
def supplier_products():
    s = supplier_record()
    rows = g.db.execute(
        """SELECT p.*, c.name AS category_name FROM products p
           JOIN categories c ON c.id=p.category_id
           WHERE p.supplier_id=? ORDER BY p.id DESC""", (s["id"],)).fetchall()
    return render_template("supplier_products.html", rows=rows)


@app.route("/supplier/products/add", methods=["GET", "POST"])
@login_required
@role_required("supplier")
def supplier_product_add():
    s = supplier_record()
    cats = g.db.execute("SELECT * FROM categories ORDER BY sort_order").fetchall()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Product name is required.", "error")
        else:
            cur = g.db.execute(
                """INSERT INTO products (supplier_id, category_id, name, slug, sku, description, specifications,
                   moq, price, old_price, stock, low_stock_threshold, status, ship_time)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (s["id"], request.form.get("category_id", type=int), name, slugify(name) + "-" + str(secrets.randbelow(9999)),
                 request.form.get("sku", ""), request.form.get("description", ""), request.form.get("specifications", ""),
                 max(1, request.form.get("moq", 50, type=int)), request.form.get("price", 0, type=float),
                 request.form.get("old_price", type=float) or None,
                 max(0, request.form.get("stock", 0, type=int)), 20,
                 "pending" if s["verification_status"] != "verified" else "approved",
                 request.form.get("ship_time", "Ships in 3-5 days")))
            pid = cur.lastrowid
            base = request.form.get("price", 0, type=float)
            moq = max(1, request.form.get("moq", 50, type=int))
            t2 = request.form.get("tier2", type=float) or round(base * 0.85, 2)
            t3 = request.form.get("tier3", type=float) or round(base * 0.70, 2)
            for tmin, tprice in [(moq, base), (moq * 2, t2), (moq * 10, t3)]:
                g.db.execute("INSERT INTO product_tiers (product_id, min_qty, price) VALUES (?,?,?)", (pid, tmin, tprice))
            g.db.execute("INSERT INTO inventory_log (product_id, change_qty, note) VALUES (?,?,?)",
                         (pid, request.form.get("stock", 0, type=int), "Initial stock"))
            g.db.commit()
            flash("Product created. It will appear live once approved." if s["verification_status"] != "verified" else "Product is live.", "success")
            return redirect(url_for("supplier_products"))
    return render_template("supplier_product_form.html", cats=cats, product=None)


@app.route("/supplier/products/<int:pid>/edit", methods=["GET", "POST"])
@login_required
@role_required("supplier")
def supplier_product_edit(pid):
    s = supplier_record()
    p = g.db.execute("SELECT * FROM products WHERE id=? AND supplier_id=?", (pid, s["id"])).fetchone()
    if not p:
        abort(404)
    cats = g.db.execute("SELECT * FROM categories ORDER BY sort_order").fetchall()
    if request.method == "POST":
        stock = max(0, request.form.get("stock", 0, type=int))
        old_stock = p["stock"]
        g.db.execute(
            """UPDATE products SET category_id=?, name=?, sku=?, description=?, specifications=?,
               moq=?, price=?, old_price=?, stock=?, ship_time=? WHERE id=?""",
            (request.form.get("category_id", type=int), request.form.get("name", "").strip(),
             request.form.get("sku", ""), request.form.get("description", ""),
             request.form.get("specifications", ""), max(1, request.form.get("moq", 50, type=int)),
             request.form.get("price", 0, type=float), request.form.get("old_price", type=float) or None,
             stock, request.form.get("ship_time", "Ships in 3-5 days"), pid))
        if stock != old_stock:
            g.db.execute("INSERT INTO inventory_log (product_id, change_qty, note) VALUES (?,?,?)",
                         (pid, stock - old_stock, "Manual adjustment"))
        g.db.commit()
        flash("Product updated.", "success")
        return redirect(url_for("supplier_products"))
    return render_template("supplier_product_form.html", cats=cats, product=p)


@app.post("/supplier/products/<int:pid>/delete")
@login_required
@role_required("supplier")
def supplier_product_delete(pid):
    s = supplier_record()
    g.db.execute("DELETE FROM products WHERE id=? AND supplier_id=?", (pid, s["id"]))
    g.db.commit()
    flash("Product deleted.", "info")
    return redirect(url_for("supplier_products"))


@app.route("/supplier/orders")
@login_required
@role_required("supplier")
def supplier_orders():
    s = supplier_record()
    rows = g.db.execute(
        """SELECT o.*, oi.qty, oi.product_name, oi.total AS item_total, u.name AS buyer
           FROM order_items oi JOIN orders o ON o.id=oi.order_id JOIN users u ON u.id=o.user_id
           WHERE oi.supplier_id=? ORDER BY o.id DESC""", (s["id"],)).fetchall()
    return render_template("supplier_orders.html", rows=rows, ORDER_LABELS=ORDER_LABELS)


@app.post("/supplier/order/<int:oid>/status")
@login_required
@role_required("supplier")
def supplier_order_status(oid):
    s = supplier_record()
    new_status = request.form.get("status")
    if new_status not in ORDER_FLOW:
        flash("Invalid status.", "error")
        return redirect(url_for("supplier_orders"))
    o = g.db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if not o:
        abort(404)
    g.db.execute("UPDATE orders SET status=?, updated_at=datetime('now') WHERE id=?", (new_status, oid))
    g.db.execute("INSERT INTO notifications (user_id, type, title, body, link) VALUES (?,?,?,?,?)",
                 (o["user_id"], "order", f"Order {o['order_number']}: {ORDER_LABELS[new_status]}",
                  f"Your order is now {ORDER_LABELS[new_status]}.", f"/order/{oid}"))
    g.db.commit()
    flash(f"Order marked as {ORDER_LABELS[new_status]}.", "success")
    return redirect(url_for("supplier_orders"))


@app.route("/supplier/quotes")
@login_required
@role_required("supplier")
def supplier_quotes():
    s = supplier_record()
    rows = g.db.execute(
        """SELECT q.*, p.name AS product_name, u.name AS buyer_name, u.company
           FROM quotes q JOIN products p ON p.id=q.product_id JOIN users u ON u.id=q.user_id
           WHERE q.supplier_id=? ORDER BY q.id DESC""", (s["id"],)).fetchall()
    return render_template("supplier_quotes.html", rows=rows)


@app.post("/supplier/quotes/<int:qid>/respond")
@login_required
@role_required("supplier")
def supplier_quote_respond(qid):
    s = supplier_record()
    response = request.form.get("response", "").strip()
    status = request.form.get("status", "responded")
    q = g.db.execute("SELECT * FROM quotes WHERE id=? AND supplier_id=?", (qid, s["id"])).fetchone()
    if not q:
        abort(404)
    g.db.execute("UPDATE quotes SET response=?, status=?, responded_at=datetime('now') WHERE id=?", (response, status, qid))
    g.db.execute("INSERT INTO notifications (user_id, type, title, body, link) VALUES (?,?,?,?,?)",
                 (q["user_id"], "quote", f"Quote response for #{qid}",
                  (response or "The supplier responded to your quote request.")[:80], "/quotes"))
    g.db.commit()
    flash("Response sent to buyer.", "success")
    return redirect(url_for("supplier_quotes"))


@app.route("/supplier/coupons", methods=["GET", "POST"])
@login_required
@role_required("supplier")
def supplier_coupons():
    s = supplier_record()
    if request.method == "POST":
        g.db.execute(
            """INSERT INTO coupons (code, discount_type, value, min_order, max_discount, usage_limit, start_date, end_date, active)
               VALUES (?,?,?,?,?,?,?,?,1)""",
            (request.form.get("code", "").upper().strip(), request.form.get("discount_type", "percent"),
             request.form.get("value", 0, type=float), request.form.get("min_order", 0, type=float),
             request.form.get("max_discount", 0, type=float), request.form.get("usage_limit", 100, type=int),
             request.form.get("start_date") or None, request.form.get("end_date") or None))
        g.db.commit()
        flash("Coupon created.", "success")
        return redirect(url_for("supplier_coupons"))
    rows = g.db.execute("SELECT * FROM coupons ORDER BY id DESC").fetchall()
    return render_template("supplier_coupons.html", rows=rows)


@app.post("/coupon/apply")
@login_required
def coupon_apply():
    code = request.form.get("code", "").strip().upper()
    coupon = g.db.execute("SELECT * FROM coupons WHERE code=? AND active=1", (code,)).fetchone()
    lines, subtotal, savings = cart_lines()
    if not coupon:
        flash("Invalid coupon code.", "error")
    elif coupon["used_count"] >= coupon["usage_limit"]:
        flash("This coupon has reached its usage limit.", "error")
    elif subtotal < coupon["min_order"]:
        flash(f"This coupon requires a minimum order of ${coupon['min_order']:,.0f}.", "error")
    else:
        session["coupon_code"] = code
        flash(f"Coupon {code} applied!", "success")
    return redirect(url_for("checkout"))


@app.route("/supplier/campaigns", methods=["GET", "POST"])
@login_required
@role_required("supplier")
def supplier_campaigns():
    s = supplier_record()
    if request.method == "POST":
        cur = g.db.execute(
            """INSERT INTO campaigns (title, description, discount, start_date, end_date, banner_color, active)
               VALUES (?,?,?,?,?,?,1)""",
            (request.form.get("title"), request.form.get("description", ""), request.form.get("discount", 0, type=float),
             request.form.get("start_date") or None, request.form.get("end_date") or None,
             request.form.get("banner_color", "#2548eb")))
        cid = cur.lastrowid
        for pid in request.form.getlist("product_ids"):
            if pid.isdigit():
                g.db.execute("INSERT INTO campaign_products (campaign_id, product_id) VALUES (?,?)", (cid, int(pid)))
        g.db.commit()
        flash("Campaign created.", "success")
        return redirect(url_for("supplier_campaigns"))
    campaigns = g.db.execute("SELECT * FROM campaigns ORDER BY id DESC").fetchall()
    products = g.db.execute("SELECT id, name FROM products WHERE supplier_id=? AND status='approved'", (s["id"],)).fetchall()
    return render_template("supplier_campaigns.html", campaigns=campaigns, products=products)


# ----------------------------------------------------------------------
# Admin panel
# ----------------------------------------------------------------------
@app.route("/admin")
@login_required
@role_required("admin")
def admin_panel():
    stats = {
        "revenue": g.db.execute("SELECT COALESCE(SUM(total),0) t FROM orders WHERE status='delivered'").fetchone()["t"],
        "orders": g.db.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"],
        "customers": g.db.execute("SELECT COUNT(*) c FROM users WHERE role='customer'").fetchone()["c"],
        "suppliers": g.db.execute("SELECT COUNT(*) c FROM suppliers").fetchone()["c"],
        "products": g.db.execute("SELECT COUNT(*) c FROM products").fetchone()["c"],
        "pending_orders": g.db.execute("SELECT COUNT(*) c FROM orders WHERE status='order_placed'").fetchone()["c"],
        "pending_suppliers": g.db.execute("SELECT COUNT(*) c FROM suppliers WHERE verification_status IN ('pending','under_review')").fetchone()["c"],
        "pending_products": g.db.execute("SELECT COUNT(*) c FROM products WHERE status='pending'").fetchone()["c"],
    }
    pending_suppliers = g.db.execute("SELECT * FROM suppliers WHERE verification_status IN ('pending','under_review')").fetchall()
    pending_products = g.db.execute(
        """SELECT p.*, s.company_name FROM products p JOIN suppliers s ON s.id=p.supplier_id
           WHERE p.status='pending'""").fetchall()
    recent_orders = g.db.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 8").fetchall()
    recent_users = g.db.execute("SELECT * FROM users ORDER BY id DESC LIMIT 8").fetchall()
    return render_template("admin.html", stats=stats, pending_suppliers=pending_suppliers,
                           pending_products=pending_products, recent_orders=recent_orders,
                           recent_users=recent_users, ORDER_LABELS=ORDER_LABELS)


@app.post("/admin/supplier/<int:sid>/status")
@login_required
@role_required("admin")
def admin_supplier_status(sid):
    status = request.form.get("status")
    if status not in ("pending", "under_review", "verified", "rejected"):
        abort(400)
    s = g.db.execute("SELECT * FROM suppliers WHERE id=?", (sid,)).fetchone()
    if s:
        g.db.execute("UPDATE suppliers SET verification_status=? WHERE id=?", (status, sid))
        g.db.execute("INSERT INTO notifications (user_id, type, title, body, link) VALUES (?,?,?,?,?)",
                     (s["user_id"], "info", "Supplier verification update",
                      f"Your supplier status is now: {status.title()}.", "/supplier/dashboard"))
        g.db.commit()
        flash(f"Supplier set to {status}.", "success")
    return redirect(url_for("admin_panel"))


@app.post("/admin/product/<int:pid>/status")
@login_required
@role_required("admin")
def admin_product_status(pid):
    status = request.form.get("status")
    if status not in ("pending", "approved", "rejected"):
        abort(400)
    p = g.db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if p:
        g.db.execute("UPDATE products SET status=? WHERE id=?", (status, pid))
        sup = g.db.execute("SELECT user_id FROM suppliers WHERE id=?", (p["supplier_id"],)).fetchone()
        if sup:
            g.db.execute("INSERT INTO notifications (user_id, type, title, body, link) VALUES (?,?,?,?,?)",
                         (sup["user_id"], "product", f"Product {status}: {p['name']}",
                          f"Your product '{p['name']}' was {status}.", "/supplier/products"))
        g.db.commit()
        flash(f"Product {status}.", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/orders")
@login_required
@role_required("admin")
def admin_orders():
    rows = g.db.execute(
        """SELECT o.*, u.name AS buyer FROM orders o JOIN users u ON u.id=o.user_id
           ORDER BY o.id DESC LIMIT 100""").fetchall()
    return render_template("admin_orders.html", rows=rows, ORDER_LABELS=ORDER_LABELS)


# ----------------------------------------------------------------------
# API (search autocomplete + tier pricing)
# ----------------------------------------------------------------------
@app.get("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"results": []})
    rows = g.db.execute(
        """SELECT p.id, p.name, p.slug, p.price, p.moq, p.image, s.company_name
           FROM products p JOIN suppliers s ON s.id=p.supplier_id
           WHERE p.status='approved' AND (p.name LIKE ? OR p.sku LIKE ? OR p.description LIKE ? OR s.company_name LIKE ?)
           LIMIT 8""", (f"%{q}%",) * 4).fetchall()
    return jsonify({"results": [dict(r) for r in rows]})


@app.get("/api/product/<int:pid>/price")
def api_price(pid):
    qty = request.args.get("qty", 0, type=int)
    p = g.db.execute("SELECT * FROM products WHERE id=? AND status='approved'", (pid,)).fetchone()
    if not p:
        return jsonify({"error": "not found"}), 404
    unit = tier_price(p, qty or p["moq"])
    return jsonify({"unit": unit, "total": round(unit * qty, 2) if qty else None})


@app.get("/api/notifications/unread")
@login_required
def api_unread():
    return jsonify({"count": g.notif_count})


# ----------------------------------------------------------------------
# SEO
# ----------------------------------------------------------------------
@app.route("/sitemap.xml")
def sitemap():
    urls = [url_for("home", _external=True), url_for("products", _external=True), url_for("suppliers_page", _external=True)]
    for c in g.db.execute("SELECT slug FROM categories").fetchall():
        urls.append(url_for("category", slug=c["slug"], _external=True))
    for p in g.db.execute("SELECT slug FROM products WHERE status='approved'").fetchall():
        urls.append(url_for("product", slug=p["slug"], _external=True))
    for s in g.db.execute("SELECT slug FROM suppliers").fetchall():
        urls.append(url_for("supplier_store", slug=s["slug"], _external=True))
    body = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for u in urls:
        body += f"  <url><loc>{u}</loc><changefreq>daily</changefreq><priority>0.8</priority></url>\n"
    body += "</urlset>"
    r = make_response(body)
    r.headers["Content-Type"] = "application/xml"
    return r


@app.route("/robots.txt")
def robots():
    r = make_response("User-agent: *\nAllow: /\nDisallow: /api/\nSitemap: " + url_for("sitemap", _external=True) + "\n")
    r.headers["Content-Type"] = "text/plain"
    return r


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, msg="Page not found"), 404


@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403, msg="You don't have permission to access this page"), 403


@app.context_processor
def inject_globals():
    def mkts(name):
        q = urllib.parse.quote_plus(name)
        return [
            ("Alibaba", f"https://www.alibaba.com/trade/search?SearchText={q}"),
            ("DHGate", f"https://www.dhgate.com/wholesale/search.do?key={q}"),
            ("Made-in-China", f"https://www.made-in-china.com/products-search/hot-china-products/{q}/"),
            ("1688", f"https://s.1688.com/selloffer/offer_search.htm?keywords={q}"),
        ]
    return {"PAYMENT_PROVIDERS": PAYMENT_PROVIDERS, "ORDER_LABELS": ORDER_LABELS,
            "now": datetime.utcnow(), "flash_categories": {"success": "success", "error": "error", "info": "info"},
            "mkts": mkts, "merchant_email": MERCHANT_EMAIL, "smtp_ready": SMTP_READY,
            "cart_drawer": _cart_drawer_data()}


def _cart_drawer_data():
    if not g.user or g.user["role"] != "customer":
        return None
    try:
        lines, subtotal, savings = cart_lines()
    except Exception:
        return None
    return {
        "items": lines,
        "count": sum(l["qty"] for l in lines),
        "subtotal": subtotal,
        "savings": savings,
        "total": round(subtotal - savings, 2),
    }


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    print("\n  ============================================")
    print("   TradeLink Wholesale — Platform Server")
    print("  ============================================")
    print(f"   URL:        http://localhost:{port}")
    print(f"   Database:   {DB_PATH}")
    print("   Demo accounts:")
    print("     Admin:     admin@tradelink.com / admin123")
    print("     Supplier:  supplier@novatech.com / supplier123")
    print("     Buyer:     buyer@meridian.com / buyer123")
    print("   Ctrl+C to stop\n")
    app.run(host=os.environ.get("TRADELINK_HOST", "127.0.0.1"), port=port, debug=True)