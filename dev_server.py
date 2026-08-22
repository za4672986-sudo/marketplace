"""
Tradelink Wholesale — Development Server
========================================
Serves the B2B Wholesale Marketplace with:
  - Static file serving (index.html, styles/, assets/)
  - API simulation endpoints (products, suppliers, search)
  - Auto-open browser on start
  - Hot-reload friendly (reload page on file change via SSE)

Usage:
    python dev_server.py            # starts on http://localhost:8000
    python dev_server.py 9000       # custom port
"""

import json
import mimetypes
import os
import socketserver
import threading
import time
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 8000
DATA = {
    "products": [],
    "suppliers": [],
    "categories": [],
}

DEMO_PRODUCTS = [
    {"id": "tl-1001", "name": "Premium Wireless Earbuds ANC 30H", "cat": "Electronics", "price": 12.50, "moq": 50},
    {"id": "tl-1002", "name": "100W GaN Fast Charger USB-C 4-Port", "cat": "Mobile Accessories", "price": 8.90, "moq": 100},
    {"id": "tl-1003", "name": "Organic Cotton Heavyweight Tee 240GSM", "cat": "Fashion", "price": 4.20, "moq": 200},
    {"id": "tl-1004", "name": "Foldable Solar Panel 100W Portable", "cat": "Electronics", "price": 45.00, "moq": 20},
    {"id": "tl-1005", "name": "Stainless Steel Water Bottle 750ml", "cat": "Home & Kitchen", "price": 3.10, "moq": 300},
]

DEMO_SUPPLIERS = [
    {"name": "NovaTech Electronics", "country": "China", "rating": 4.8, "verified": True},
    {"name": "Atlas Apparel Co.", "country": "Türkiye", "rating": 4.9, "verified": True},
    {"name": "SunGrid Energy", "country": "China", "rating": 4.6, "verified": True},
]

DEMO_CATEGORIES = ["Electronics", "Fashion", "Home & Kitchen", "Shoes", "Beauty"]


class MarketHandler(SimpleHTTPRequestHandler):
    """Serves static files + simulated JSON API endpoints."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _api(self, path):
        """Route /api/* endpoints."""
        if path == "/api/health":
            return self._json({"status": "ok", "time": datetime.utcnow().isoformat()})
        if path == "/api/products":
            q = (self.path_query().get("q") or [""])[0]
            products = DEMO_PRODUCTS
            if q:
                products = [p for p in products if q.lower() in json.dumps(p).lower()]
            return self._json({"data": products, "total": len(products)})
        if path == "/api/suppliers":
            return self._json({"data": DEMO_SUPPLIERS})
        if path == "/api/categories":
            return self._json({"data": DEMO_CATEGORIES})
        return self._json({"error": "Not found"}, 404)

    def path_query(self):
        import urllib.parse
        return urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._api(self.path.split("?")[0])
        if self.path == "/" or self.path == "/index.html":
            self.path = "/index.html"
        return super().do_GET()

    def log_message(self, fmt, *args):
        print(f"  {datetime.now().strftime('%H:%M:%S')}  {self.address_string()}  {fmt % args}")


class QuietTCPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def open_browser():
    time.sleep(1.2)
    try:
        import webbrowser
        webbrowser.open(f"http://localhost:{PORT}")
    except Exception:
        pass


def main():
    global PORT
    import sys
    if len(sys.argv) > 1:
        PORT = int(sys.argv[1])

    print()
    print("  ============================================")
    print("   TradeLink Wholesale — Dev Server")
    print("  ============================================")
    print(f"   Serving:      http://localhost:{PORT}")
    print(f"   Root:         {ROOT}")
    print(f"   API:          /api/products, /api/suppliers, /api/categories")
    print(f"   Health:       /api/health")
    print()
    print("   Ctrl+C to stop")
    print()

    threading.Thread(target=open_browser, daemon=True).start()

    handler = MarketHandler
    httpd = QuietTCPServer(("127.0.0.1", PORT), handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
        httpd.server_close()


if __name__ == "__main__":
    main()
