"""TradeLink Wholesale — Database layer (SQLite)."""
import os
import sqlite3
import hashlib
import secrets
import json
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "marketplace.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_password(password: str, salt: str = None) -> tuple:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 120_000).hex()
    return digest, salt


def verify_password(password: str, digest: str, salt: str) -> bool:
    return hash_password(password, salt)[0] == digest


def slugify(text: str) -> str:
    import re
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "item"


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    name TEXT NOT NULL,
    company TEXT,
    role TEXT NOT NULL DEFAULT 'customer',   -- customer | supplier | admin
    country TEXT DEFAULT 'United States',
    phone TEXT,
    is_verified INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE NOT NULL REFERENCES users(id),
    company_name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    country TEXT NOT NULL,
    years_in_business INTEGER DEFAULT 1,
    business_type TEXT DEFAULT 'Manufacturer',
    description TEXT DEFAULT '',
    certifications TEXT DEFAULT '',
    verification_status TEXT DEFAULT 'pending', -- pending | under_review | verified | rejected
    response_rate INTEGER DEFAULT 95,
    response_time TEXT DEFAULT '4h',
    rating_avg REAL DEFAULT 0,
    rating_count INTEGER DEFAULT 0,
    orders_completed INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    icon TEXT DEFAULT '',
    sort_order INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
    category_id INTEGER NOT NULL REFERENCES categories(id),
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    sku TEXT,
    description TEXT DEFAULT '',
    specifications TEXT DEFAULT '',
    moq INTEGER DEFAULT 50,
    price REAL NOT NULL DEFAULT 0,
    old_price REAL,
    stock INTEGER DEFAULT 0,
    low_stock_threshold INTEGER DEFAULT 20,
    status TEXT DEFAULT 'pending',  -- pending | approved | rejected
    image TEXT DEFAULT '',
    ship_time TEXT DEFAULT 'Ships in 3-5 days',
    views INTEGER DEFAULT 0,
    sold INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS product_tiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    min_qty INTEGER NOT NULL,
    price REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS inventory_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    change_qty INTEGER NOT NULL,
    note TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS carts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    qty INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(user_id, product_id)
);
CREATE TABLE IF NOT EXISTS wishlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(user_id, product_id)
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    order_number TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'order_placed',  -- order_placed | payment_confirmed | processing | packed | shipped | in_transit | delivered
    subtotal REAL DEFAULT 0,
    discount REAL DEFAULT 0,
    shipping REAL DEFAULT 0,
    tax REAL DEFAULT 0,
    total REAL DEFAULT 0,
    payment_method TEXT DEFAULT 'bank_transfer',
    payment_status TEXT DEFAULT 'pending',  -- pending | confirmed | failed | refunded
    shipping_method TEXT DEFAULT 'standard',
    address_json TEXT DEFAULT '{}',
    coupon_code TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
    product_name TEXT NOT NULL,
    qty INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    total REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    provider TEXT DEFAULT 'bank_transfer',  -- stripe | paypal | bank_transfer | cod | wallet
    provider_ref TEXT DEFAULT '',
    amount REAL NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
    qty INTEGER NOT NULL,
    target_price REAL,
    destination TEXT DEFAULT '',
    delivery_date TEXT DEFAULT '',
    requirements TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',  -- pending | responded | accepted | closed
    response TEXT DEFAULT '',
    responded_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    supplier_id INTEGER REFERENCES suppliers(id),
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment TEXT DEFAULT '',
    is_verified_purchase INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id INTEGER NOT NULL REFERENCES users(id),
    receiver_id INTEGER NOT NULL REFERENCES users(id),
    product_id INTEGER REFERENCES products(id),
    order_id INTEGER REFERENCES orders(id),
    quote_id INTEGER REFERENCES quotes(id),
    body TEXT NOT NULL,
    is_read INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    type TEXT DEFAULT 'info',  -- order | quote | message | promo | price | stock
    title TEXT NOT NULL,
    body TEXT DEFAULT '',
    link TEXT DEFAULT '',
    is_read INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS coupons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    discount_type TEXT NOT NULL,  -- percent | fixed
    value REAL NOT NULL,
    min_order REAL DEFAULT 0,
    max_discount REAL DEFAULT 0,
    usage_limit INTEGER DEFAULT 100,
    used_count INTEGER DEFAULT 0,
    start_date TEXT,
    end_date TEXT,
    active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    discount REAL DEFAULT 0,
    start_date TEXT,
    end_date TEXT,
    banner_color TEXT DEFAULT '#2548eb',
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS campaign_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS addresses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    label TEXT DEFAULT 'Business',
    full_name TEXT NOT NULL,
    phone TEXT,
    line1 TEXT NOT NULL,
    line2 TEXT DEFAULT '',
    city TEXT NOT NULL,
    state TEXT DEFAULT '',
    zip TEXT DEFAULT '',
    country TEXT DEFAULT 'United States',
    is_default INTEGER DEFAULT 0
);
"""


def init_db():
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    seed(conn)
    conn.close()


def seed(conn: sqlite3.Connection):
    """Insert demo data only if the database is empty."""
    if conn.execute("SELECT COUNT(*) c FROM categories").fetchone()["c"] > 0:
        return

    now = datetime.utcnow()

    # Categories
    cats = [
        ("Electronics", "electronics", "electronics"), ("Mobile Accessories", "mobile-accessories", "mobile"),
        ("Fashion", "fashion", "fashion"), ("Shoes", "shoes", "shoes"),
        ("Beauty & Personal Care", "beauty-personal-care", "beauty"), ("Home & Kitchen", "home-kitchen", "home"),
        ("Sports & Fitness", "sports-fitness", "sports"), ("Toys & Kids", "toys-kids", "toys"),
        ("Automotive", "automotive", "automotive"), ("Tools & Hardware", "tools-hardware", "tools"),
        ("Office Supplies", "office-supplies", "office"), ("Jewelry & Accessories", "jewelry-accessories", "jewelry"),
        ("Health & Lifestyle", "health-lifestyle", "health"), ("Bags & Luggage", "bags-luggage", "bags"),
        ("Food & Grocery", "food-grocery", "food"), ("Industrial Products", "industrial-products", "industrial"),
    ]
    for i, (name, slug, icon) in enumerate(cats):
        conn.execute("INSERT INTO categories (name, slug, icon, sort_order) VALUES (?,?,?,?)", (name, slug, icon, i))

    # Users: admin + 4 suppliers + 3 customers
    admin_pw = hash_password("admin123")
    conn.execute("INSERT INTO users (email, password_hash, salt, name, company, role, country, is_verified) VALUES (?,?,?,?,?,?,?,1)",
                 ("admin@tradelink.com", admin_pw[0], admin_pw[1], "TradeLink Admin", "TradeLink HQ", "admin", "United States"))

    supplier_data = [
        ("supplier@novatech.com", "NovaTech Electronics", "Shenzhen, China", 12, "Manufacturer",
         "Consumer electronics, smart devices and accessories with 12 years of export experience.",
         "ISO 9001, CE, FCC", "verified", 4.8, 86000),
        ("supplier@atlasapparel.com", "Atlas Apparel Co.", "Istanbul, Türkiye", 18, "Manufacturer",
         "Garments, textiles and private-label apparel serving 400+ retail chains globally.",
         "OEKO-TEX, BSCI, GOTS", "verified", 4.9, 124000),
        ("supplier@greenpack.com", "GreenPack Solutions", "Kaohsiung, Taiwan", 9, "Manufacturer",
         "Sustainable packaging and food containers. FSC-certified production lines.",
         "ISO 14001, FSC", "verified", 4.7, 31200),
        ("supplier@sungrid.com", "SunGrid Energy", "Ningbo, China", 15, "Manufacturer",
         "Solar panels and renewable energy systems for distributors and EPC contractors.",
         "TÜV, CE, CQC", "under_review", 4.6, 18900),
    ]
    sup_ids = []
    for email, company, country, years, btype, desc, certs, vstatus, rating, orders in supplier_data:
        pw = hash_password("supplier123")
        cur = conn.execute("INSERT INTO users (email, password_hash, salt, name, company, role, country, is_verified) VALUES (?,?,?,?,?,?,?,1)",
                           (email, pw[0], pw[1], company, company, "supplier", country.split(", ")[0]))
        uid = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO suppliers (user_id, company_name, slug, country, years_in_business, business_type, description, certifications, verification_status, rating_avg, orders_completed) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (uid, company, slugify(company), country, years, btype, desc, certs, vstatus, rating, orders))
        sup_ids.append(cur.lastrowid)

    customer_data = [
        ("buyer@meridian.com", "Marcus Chen", "Meridian Retail", "United States"),
        ("buyer@urbanmart.com", "Priya Sharma", "UrbanCart Retail", "India"),
        ("buyer@saharatrade.com", "Amira Hassan", "Sahara Trade", "UAE"),
    ]
    cust_ids = []
    for email, name, company, country in customer_data:
        pw = hash_password("buyer123")
        cur = conn.execute("INSERT INTO users (email, password_hash, salt, name, company, role, country, is_verified) VALUES (?,?,?,?,?,?,?,1)",
                           (email, pw[0], pw[1], name, company, "customer", country))
        cust_ids.append(cur.lastrowid)

    # Products
    products = [
        ("Premium Wireless Earbuds ANC 30H", "tl-1001", 0, 0, 12.50, 19.00, 1250, "approved", "Wireless earbuds with active noise cancellation, 30h battery life and IPX5 water resistance.",
         "Bluetooth 5.3 | ANC -35dB | 30h battery | USB-C | IPX5 | Weight 4.5g/ear", 50, 3, 3800, 2314),
        ("100W GaN Fast Charger USB-C 4-Port", "tl-1002", 1, 0, 8.90, 14.50, 3400, "approved", "100W GaN fast charger with 4 USB-C/A ports, universal compatibility.",
         "100W max | GaN II | 4 ports | 110-240V | CE/FCC | 18 month warranty", 100, 2, 15200, 1890),
        ("Organic Cotton Heavyweight Tee 240GSM", "tl-1003", 2, 2, 4.20, 6.80, 8900, "approved", "240GSM organic cotton t-shirt, pre-shrunk, available in 12 colors, private label ready.",
         "240GSM | 100% organic cotton | sizes S-4XL | OEKO-TEX | 12 colors", 200, 5, 42000, 4512),
        ("Foldable Solar Panel 100W Portable", "tl-1004", 3, 0, 45.00, 68.00, 420, "approved", "Foldable 100W monocrystalline solar panel for off-grid and mobile power.",
         "100W | monocrystalline 23% | IP67 | folding 4-panel | 5m cable", 20, 7, 2900, 867),
        ("Stainless Steel Water Bottle 750ml Insulated", "tl-1005", 2, 5, 3.10, 5.20, 21500, "approved", "Vacuum insulated stainless steel bottle, keeps cold 24h / hot 12h.",
         "750ml | 18/8 steel | double-wall vacuum | leakproof | 8 colors", 300, 4, 98000, 3201),
        ("Pro Running Shoes Breathable Mesh", "tl-1006", 1, 3, 9.80, 16.00, 680, "approved", "Lightweight breathable running shoes with cushioned EVA sole.",
         "EVA midsole | mesh upper | sizes 36-46 | 8 colors", 120, 6, 7600, 1456),
        ("Vitamin C Serum 30ml Private Label", "tl-1007", 2, 4, 2.75, 4.90, 5600, "approved", "20% Vitamin C brightening serum, private label packaging available.",
         "20% Vit C | 30ml amber bottle | pH 5.5 | GMP certified", 500, 3, 31000, 2987),
        ("Smart LED Strip 5M RGB App Control", "tl-1008", 0, 0, 5.40, 9.90, 7800, "approved", "5M smart LED strip with app and voice control, 16M colors.",
         "5M | RGB | WiFi+BLE | 16M colors | app + Alexa/Google", 150, 3, 65000, 5231),
        ("Eco Kraft Food Boxes 1000ml (Pack 50)", "tl-1009", 2, 14, 7.20, 10.50, 4500, "approved", "Compostable kraft food boxes with leak-proof PLA lining, pack of 50.",
         "1000ml | kraft + PLA | compostable | microwave safe | 50-pack", 40, 5, 28000, 1123),
        ("Cordless Drill 20V Max Kit with 2 Batteries", "tl-1010", 0, 9, 23.00, 35.00, 380, "approved", "20V cordless drill kit with 2 batteries, charger and carry case.",
         "20V | 2x 2.0Ah batteries | 28Nm torque | keyless chuck | 1yr warranty", 30, 4, 5200, 2109),
        ("Ceramic Dinnerware Set 16-Piece", "tl-1011", 1, 5, 18.40, 28.00, 950, "approved", "16-piece porcelain dinnerware set for 4, dishwasher and microwave safe.",
         "16pc | porcelain | dishwasher safe | microwave safe", 25, 8, 4300, 978),
        ("Kids Educational Building Blocks 500pc", "tl-1012", 2, 7, 6.90, 11.00, 6100, "approved", "500-piece educational building blocks, BPA-free, compatible with major brands.",
         "500pc | BPA-free ABS | EN71/ASTM | storage box", 80, 3, 47000, 3645),
        ("Dash Cam 4K Front & Rear Dual", "tl-1013", 0, 8, 32.00, 49.00, 540, "pending", "4K front and rear dash cam with parking mode and GPS logging.",
         "4K+1080p | dual lens | GPS | parking mode | 64GB max", 25, 4, 8900, 1543),
        ("Silicone Lunch Boxes Set of 3 Collapsible", "tl-1014", 2, 14, 4.50, 7.80, 3900, "approved", "Set of 3 collapsible silicone lunch boxes, leakproof and dishwasher safe.",
         "3 sizes | food-grade silicone | collapsible | dishwasher safe", 100, 5, 21000, 876),
        ("Mechanical Gaming Keyboard RGB Hot-Swap", "tl-1015", 0, 0, 15.60, 24.00, 2200, "approved", "Hot-swappable mechanical gaming keyboard with per-key RGB.",
         "Hot-swap | per-key RGB | 104 keys | USB-C | 5 switch options", 60, 3, 38000, 2876),
        ("Reusable Shopping Tote Canvas 500D", "tl-1016", 2, 13, 1.45, 2.60, 18000, "approved", "Heavy-duty 500D canvas shopping tote, custom printing available.",
         "500D canvas | 38x42cm | 20kg capacity | custom print", 500, 6, 120000, 2104),
    ]
    # (name, sku, supplier_idx, cat_idx, price, old, stock, status, desc, spec, moq, ship_days, sold, reviews)
    for (name, sku, si, ci, price, old, stock, status, desc, spec, moq, days, sold, reviews) in products:
        sid = sup_ids[si]
        cid = ci + 1
        cur = conn.execute(
            "INSERT INTO products (supplier_id, category_id, name, slug, sku, description, specifications, moq, price, old_price, stock, status, ship_time, sold) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sid, cid, name, slugify(name), sku, desc, spec, moq, price, old, stock, status, f"Ships in {days} days", sold))
        pid = cur.lastrowid
        # Tier pricing
        tiers = [(moq, price), (moq * 2, round(price * 0.85, 2)), (moq * 10, round(price * 0.70, 2))]
        for tmin, tprice in tiers:
            conn.execute("INSERT INTO product_tiers (product_id, min_qty, price) VALUES (?,?,?)", (pid, tmin, tprice))
        # Reviews
        for ri in range(2):
            rating = 4 if ri == 0 else 5
            conn.execute("INSERT INTO reviews (user_id, product_id, supplier_id, rating, comment, is_verified_purchase) VALUES (?,?,?,?,?,1)",
                         (cust_ids[ri % 3], pid, sid, rating,
                          "Solid quality for the wholesale price. Reordered twice." if ri == 0 else "Fast shipping and consistent stock. Great partner for bulk orders."))

    # Coupons
    conn.execute("INSERT INTO coupons (code, discount_type, value, min_order, max_discount, usage_limit, start_date, end_date, active) VALUES (?,?,?,?,?,?,?,?,1)",
                 ("WELCOME10", "percent", 10, 100, 50, 500, now.isoformat(), (now + timedelta(days=90)).isoformat()))
    conn.execute("INSERT INTO coupons (code, discount_type, value, min_order, max_discount, usage_limit, start_date, end_date, active) VALUES (?,?,?,?,?,?,?,?,1)",
                 ("BULK50", "fixed", 50, 500, 0, 200, now.isoformat(), (now + timedelta(days=45)).isoformat()))
    conn.execute("INSERT INTO coupons (code, discount_type, value, min_order, max_discount, usage_limit, start_date, end_date, active) VALUES (?,?,?,?,?,?,?,?,1)",
                 ("FLASH20", "percent", 20, 200, 150, 300, now.isoformat(), (now + timedelta(days=7)).isoformat()))

    # Campaigns
    cur = conn.execute("INSERT INTO campaigns (title, description, discount, start_date, end_date, banner_color) VALUES (?,?,?,?,?,?)",
                       ("Mega Wholesale Sale", "Up to 30% off across electronics, apparel and home goods. Stock up before prices rise.", 20,
                        now.isoformat(), (now + timedelta(days=14)).isoformat(), "#2548eb"))
    cid = cur.lastrowid
    for pid in conn.execute("SELECT id FROM products WHERE status='approved' LIMIT 6").fetchall():
        conn.execute("INSERT INTO campaign_products (campaign_id, product_id) VALUES (?,?)", (cid, pid["id"]))

    # Some orders
    for ci, cust in enumerate(cust_ids):
        prods = conn.execute("SELECT * FROM products WHERE status='approved' LIMIT 4 OFFSET ?", (ci * 2,)).fetchall()
        subtotal = 0
        items = []
        for i, p in enumerate(prods):
            qty = p["moq"] * (i + 1)
            unit = p["price"]
            items.append((p, qty, unit))
            subtotal += unit * qty
        onum = "TL-" + str(100000 + ci * 137)
        status = ["delivered", "in_transit", "processing"][ci]
        conn.execute("INSERT INTO orders (user_id, order_number, status, subtotal, shipping, tax, total, payment_method, payment_status, shipping_method, address_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (cust, onum, status, subtotal, 0, round(subtotal * 0.05, 2), round(subtotal * 1.05, 2),
                      "bank_transfer", "confirmed" if ci < 2 else "pending", "sea_freight",
                      json.dumps({"full_name": "Business Buyer", "line1": "12 Commerce St", "city": "New York", "country": "United States"}),
                      (now - timedelta(days=3 * (ci + 1))).isoformat(), (now - timedelta(days=2 * (ci + 1))).isoformat()))
        oid = conn.execute("SELECT last_insert_rowid() r").fetchone()["r"]
        for p, qty, unit in items:
            conn.execute("INSERT INTO order_items (order_id, product_id, supplier_id, product_name, qty, unit_price, total) VALUES (?,?,?,?,?,?,?)",
                         (oid, p["id"], p["supplier_id"], p["name"], qty, unit, round(unit * qty, 2)))
        conn.execute("INSERT INTO payments (order_id, provider, amount, status) VALUES (?,?,?,?)",
                     (oid, "bank_transfer", round(subtotal * 1.05, 2), "confirmed" if ci < 2 else "pending"))

    # A couple of quotes + messages + notifications
    conn.execute("INSERT INTO quotes (user_id, product_id, supplier_id, qty, target_price, destination, delivery_date, requirements) VALUES (?,?,?,?,?,?,?,?)",
                 (cust_ids[0], 1, sup_ids[0], 5000, 9.50, "Los Angeles, USA", "2026-10-15", "Private label packaging with our logo. Need QC samples first."))
    conn.execute("INSERT INTO quotes (user_id, product_id, supplier_id, qty, target_price, destination, delivery_date, requirements, status, response) VALUES (?,?,?,?,?,?,?,?,?,?)",
                 (cust_ids[1], 3, sup_ids[1], 10000, 2.60, "Mumbai, India", "2026-09-30", "Mixed color split 50/50.", "responded",
                  "We can do $2.70/unit at 10,000 pcs with your color split. Samples available in 7 days."))
    conn.execute("INSERT INTO messages (sender_id, receiver_id, product_id, body) VALUES (?,?,?,?)",
                 (cust_ids[0], sup_ids[0] + 1, 1, "Hi, do you offer OEM branding on the earbuds? We need 5,000 units."))
    conn.execute("INSERT INTO messages (sender_id, receiver_id, product_id, body, is_read) VALUES (?,?,?,?,1)",
                 (sup_ids[0] + 1, cust_ids[0], 1, "Yes — OEM branding available with 30% deposit. Samples ship in 5 days."))
    for u in cust_ids:
        conn.execute("INSERT INTO notifications (user_id, type, title, body, link) VALUES (?,?,?,?,?)",
                     (u, "promo", "FLASH20: 20% off flash sale", "Extra 20% off wholesale orders over $200 this week.", "/products"))

    conn.commit()