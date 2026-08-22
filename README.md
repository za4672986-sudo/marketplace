# TradeLink Wholesale — B2B Wholesale Marketplace

A premium, production-designed B2B wholesale e-commerce marketplace for manufacturers, wholesalers, distributors, retailers, and bulk buyers.

The repository contains **two builds**:

1. **Full Platform (Flask + SQLite)** — the real marketplace: auth, carts, orders, quotes, messaging, supplier & admin dashboards. Runs on **http://localhost:5000**.
2. **Static Prototype** — the complete design/interaction prototype on the homepage. Runs on **http://localhost:8000**.

---

## Full Platform (recommended)

### Run

```
pip install flask
python app.py
```

Then open **http://localhost:5000**. The database (`marketplace.db`) is created and seeded automatically on first run.

### Demo accounts

| Role | Email | Password |
|------|-------|----------|
| Buyer | `buyer@meridian.com` | `buyer123` |
| Supplier | `supplier@novatech.com` | `supplier123` |
| Admin | `admin@tradelink.com` | `admin123` |

### What works
- **Auth** — register/login/logout (PBKDF2 hashing), role guards (customer / supplier / admin)
- **Buyer** — search + filters + sort, category pages, product detail with **live tier pricing** (MOQ / 2× / 10×), cart grouped by supplier, multi-step checkout with coupons & payment methods, orders with tracking timeline, wishlist, bulk **quote requests**, reviews (verified-purchase badge), in-platform **messaging**, notifications, saved addresses, dashboard
- **Supplier** — dashboard with stats & low-stock alerts, product CRUD, order status management, quote responses, coupons, sale campaigns
- **Admin** — marketplace stats, supplier verification queue, product approval queue, all orders
- **Coupons** — seeded: `WELCOME10` (10%, min $100, max $50), `BULK50` (fixed $50, min $500), `FLASH20` (20%, min $200, max $150)
- **API** — `GET /api/search?q=`, `GET /api/product/<id>/price?qty=`, `GET /api/notifications/unread`

### Payments
Gateway integrations are **integration points**, never hardcoded secrets: `PAYMENT_PROVIDERS` in `app.py` — bank transfer and COD enabled; Stripe/PayPal require environment keys (documented in code) to enable.

**Real wallet channels** (enabled): EasyPaisa, JazzCash (Pakistan), bKash (Bangladesh), GCash (Philippines), M-PESA (Kenya). In this build the gateway callback is simulated via the "I've Sent the Payment" button on the order page — the endpoint `POST /order/<id>/pay` is where each provider's real webhook connects.

**Email notifications via Gmail** (merchant: `za4672986@gmail.com`): set these env vars to send order/payment emails from your Gmail:
```
TRADELINK_SMTP_USER=za4672986@gmail.com
TRADELINK_SMTP_PASS=<Gmail App Password>   # Google Account > Security > 2-Step Verification > App passwords
```
(host/port default to smtp.gmail.com:587; `TRADELINK_MERCHANT_EMAIL` overrides the shown merchant contact.)

### Tests (manual)
```
python -c "from db import init_db; init_db()"   # reset database
python app.py                                    # start server
```

---

## Static Prototype

### Quick Start

### Option A: One-click launch (recommended)

Double-click `start.bat` — it starts the dev server and opens your browser automatically.

### Option B: Manual

```
python dev_server.py
```

Then open **http://localhost:8000** in your browser.

### Custom port

```
python dev_server.py 9000
```

---

## What's Inside

### Pages & Sections (live on the homepage)
| # | Section | Status |
|---|---------|--------|
| 1 | Premium sticky navbar (search, autocomplete, wishlist, cart, account) | ✅ |
| 2 | Hero with floating trust cards + animated counters | ✅ |
| 3 | Popular Categories (16 categories) | ✅ |
| 4 | Wholesale Deals with tiered bulk pricing tables | ✅ |
| 5 | Flash Wholesale Sale with **live countdown timer** | ✅ |
| 6 | Product cards (verified badge, sale badge, MOQ, stock bar, quick view) | ✅ |
| 7 | Best Sellers | ✅ |
| 8 | Verified Suppliers marketplace | ✅ |
| 9 | New Arrivals | ✅ |
| 10 | Why Businesses Choose TradeLink (trust section) | ✅ |
| 11 | Supplier CTA banner with stats | ✅ |
| 12 | Testimonials | ✅ |
| 13 | Newsletter | ✅ |
| 14 | Premium footer (7 columns, socials, payment badges) | ✅ |
| 15 | Mobile bottom navigation (Home/Categories/Search/Cart/Account) | ✅ |

### Working Features (real interactivity)
- **Search with autocomplete** — live product suggestions, trending searches, category suggestions
- **Cart** — multi-supplier grouping, tiered wholesale pricing auto-calculated, bulk savings display
- **Wishlist** — with counter and heart toggle
- **Quick View modal** — full product info, quantity tier table, MOQ quantity selector
- **Countdown timer** — functional flash sale countdown
- **Animated counters** — stats count up on scroll
- **Account dropdown** — language/currency selectors, sign-in modal
- **Mobile drawer menu** — full navigation on mobile
- **Toast notifications** — add-to-cart, wishlist, subscribe confirmations
- **Scroll reveal animations** — premium entrance effects
- **Newsletter form** — validated, with success toast

### Design System
- Custom brand: **TradeLink** — deep indigo primary + amber accent, serif display font + Inter body
- Full token set: colors (50–950 scale), shadows, radii, easing, type scale
- Consistent components: buttons, badges, chips, cards, inputs, modals, tables

### API (simulated, extensible)
```
GET /api/health        → {"status": "ok", ...}
GET /api/products      → list of products
GET /api/products?q=x  → filtered search
GET /api/suppliers     → supplier list
GET /api/categories    → category list
```

---

## Architecture Roadmap (for the full production build)

The platform is now a **fully working Flask + SQLite application**. For scale-out production:

### Phase 2 — Frontend framework
Migrate templates to **Next.js + TypeScript + Tailwind**, with:
- `/product/[slug]`, `/category/[slug]`, `/supplier/[slug]` routes
- SSR/ISR for SEO, code splitting, image optimization

### Phase 3 — Backend & database
- PostgreSQL + SQLAlchemy migrations (current SQLite schema documented in `db.py`)
- Redis for sessions, search index, and queue workers

### Phase 4 — Services & integrations
- Auth: JWT + refresh tokens, OAuth (Google), 2FA
- Payments: Stripe/PayPal adapters behind the existing `PAYMENT_PROVIDERS` config
- Search: full-text search across name, SKU, category, brand, supplier, tags
- Storage: S3-compatible bucket for product images
- Email: transactional + notification service

---

## Security Notes
- No API keys, secrets, or credentials in this repository
- Payment processing is **not** hardcoded — integration points are documented
- Passwords hashed with PBKDF2-SHA256 (120k iterations)
- Session signing key: fixed per database in dev (`TRADELINK_SECRET` env var overrides in production)

## Project Structure
```
B2B-Marketplace/
├── app.py              ← Flask platform (port 5000)
├── db.py               ← SQLite schema + seed data
├── marketplace.db      ← created on first run
├── index.html          ← Static homepage prototype (port 8000)
├── dev_server.py       ← Python dev server for the prototype
├── start.bat           ← One-click launcher (prototype)
├── static/
│   └── app.css             ← Platform design system
├── templates/              ← Platform Jinja2 templates
│   ├── base.html, home.html, products.html, category.html
│   ├── product.html, cart.html, checkout.html, orders.html, order.html
│   ├── auth.html, customer_dashboard.html, _dash_sidebar.html
│   ├── wishlist.html, quotes.html, messages.html, notifications.html
│   ├── addresses.html, suppliers.html, supplier.html
│   ├── supplier_dashboard.html, _supplier_sidebar.html
│   ├── supplier_products.html, supplier_product_form.html
│   ├── supplier_orders.html, supplier_quotes.html
│   ├── supplier_coupons.html, supplier_campaigns.html
│   ├── admin.html, admin_orders.html, error.html
├── styles/                 ← Prototype CSS
│   ├── design-system.css, global.css, navbar.css, hero.css
├── assets/                 ← (future) seed data / DB schemas
└── components/ layouts/ pages/  ← (future) framework routes
```
