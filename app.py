import json
import mimetypes
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
DB_PATH = BASE_DIR / "shops.db"
HOST = "0.0.0.0"
PORT = 8000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shops (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                owner_key TEXT NOT NULL,
                config_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_logs (
                id TEXT PRIMARY KEY,
                shop_slug TEXT NOT NULL,
                user_message TEXT NOT NULL,
                bot_reply TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(shop_slug) REFERENCES shops(slug)
            )
            """
        )
        conn.commit()


def slugify(text: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return base or "shop"


def unique_slug(name: str) -> str:
    base = slugify(name)
    slug = base
    with get_db() as conn:
        i = 1
        while conn.execute("SELECT 1 FROM shops WHERE slug = ?", (slug,)).fetchone():
            i += 1
            slug = f"{base}-{i}"
    return slug


def parse_json_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0") or 0)
    raw = handler.rfile.read(length) if length else b"{}"
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return {}


def fetch_shop(slug: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM shops WHERE slug = ?", (slug,)).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "slug": row["slug"],
        "owner_key": row["owner_key"],
        "config": json.loads(row["config_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def safe_shop_payload(shop: dict) -> dict:
    safe = dict(shop)
    safe.pop("owner_key", None)
    return safe


def generate_response(shop: dict, user_message: str) -> str:
    config = shop.get("config", {})
    message = user_message.lower().strip()

    for item in config.get("qna", []):
        q = str(item.get("question", "")).strip().lower()
        a = str(item.get("answer", "")).strip()
        if q and q in message and a:
            return a

    greetings = ["hello", "hi", "namaste", "hey", "salam"]
    if any(g in message for g in greetings):
        return f"Namaste! {shop['name']} AI Assistant me aapka swagat hai."

    rules = config.get("rules", [])
    if any(k in message for k in ["return", "refund"]):
        for rule in rules:
            if any(k in rule.lower() for k in ["return", "refund"]):
                return f"Policy: {rule}"

    timings = config.get("timings", "")
    if any(k in message for k in ["timing", "open", "close", "time"]):
        if timings:
            return f"Shop timing: {timings}"

    products = config.get("products", [])
    if any(k in message for k in ["product", "available", "milta", "stock"]):
        if products:
            return "Available products: " + ", ".join(products[:15])

    if rules:
        return f"Important rule: {rules[0]}"

    return "Aap product, timing, delivery, policy ya order related question pooch sakte hain."


class ShopAIHandler(BaseHTTPRequestHandler):
    server_version = "ShopAI/1.0"

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status: int, data: dict | list) -> None:
        self._send(status, json.dumps(data).encode("utf-8"), "application/json; charset=utf-8")

    def serve_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        ctype, _ = mimetypes.guess_type(path.name)
        self._send(HTTPStatus.OK, path.read_bytes(), f"{ctype or 'application/octet-stream'}")

    def serve_html(self, filename: str) -> None:
        self.serve_file(TEMPLATES_DIR / filename)

    def parse_shop_slug(self, prefix: str) -> str | None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith(prefix):
            return None
        remainder = parsed.path[len(prefix):]
        if "/" in remainder:
            return None
        return remainder or None

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self.serve_html("index.html")
            return

        if path == "/health":
            self.send_json(HTTPStatus.OK, {"status": "ok", "time": utc_now()})
            return

        if path.startswith("/static/"):
            rel = path.removeprefix("/static/")
            file_path = (STATIC_DIR / rel).resolve()
            if STATIC_DIR.resolve() not in file_path.parents and file_path != STATIC_DIR.resolve():
                self.send_json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
                return
            self.serve_file(file_path)
            return

        if path.startswith("/shop/"):
            slug = self.parse_shop_slug("/shop/")
            if not slug:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            if not fetch_shop(slug):
                self.serve_html("not_found.html")
                return
            self.serve_html("shop.html")
            return

        if path == "/api/shops":
            params = parse_qs(parsed.query)
            include_keys = params.get("include_keys", ["false"])[0].lower() == "true"
            with get_db() as conn:
                rows = conn.execute("SELECT * FROM shops ORDER BY created_at DESC").fetchall()
            shops = []
            for row in rows:
                item = {
                    "id": row["id"],
                    "name": row["name"],
                    "slug": row["slug"],
                    "config": json.loads(row["config_json"]),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                if include_keys:
                    item["owner_key"] = row["owner_key"]
                shops.append(item)
            self.send_json(HTTPStatus.OK, {"shops": shops})
            return

        if path.startswith("/api/shops/") and not path.endswith("/logs"):
            slug = self.parse_shop_slug("/api/shops/")
            if not slug:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "shop not found"})
                return
            shop = fetch_shop(slug)
            if not shop:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "shop not found"})
                return
            self.send_json(HTTPStatus.OK, safe_shop_payload(shop))
            return

        if path.startswith("/api/shops/") and path.endswith("/logs"):
            slug = path.split("/")[3] if len(path.split("/")) > 3 else ""
            shop = fetch_shop(slug)
            if not shop:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "shop not found"})
                return
            owner_key = self.headers.get("X-Owner-Key", "")
            if owner_key != shop["owner_key"]:
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "owner key invalid"})
                return
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT user_message, bot_reply, created_at FROM chat_logs WHERE shop_slug = ? ORDER BY created_at DESC LIMIT 200",
                    (slug,),
                ).fetchall()
            logs = [{"user_message": r[0], "bot_reply": r[1], "created_at": r[2]} for r in rows]
            self.send_json(HTTPStatus.OK, {"logs": logs})
            return

        self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        path = urlparse(self.path).path

        if path == "/api/shops":
            payload = parse_json_body(self)
            name = str(payload.get("name", "")).strip()
            if not name:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": "name is required"})
                return

            slug = unique_slug(name)
            owner_key = uuid.uuid4().hex
            now = utc_now()
            config = {
                "rules": payload.get("rules", []),
                "timings": payload.get("timings", ""),
                "products": payload.get("products", []),
                "qna": payload.get("qna", []),
                "contact": payload.get("contact", ""),
            }
            record_id = str(uuid.uuid4())
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO shops (id, name, slug, owner_key, config_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (record_id, name, slug, owner_key, json.dumps(config), now, now),
                )
                conn.commit()

            host = self.headers.get("Host", f"localhost:{PORT}")
            self.send_json(
                HTTPStatus.CREATED,
                {
                    "id": record_id,
                    "name": name,
                    "slug": slug,
                    "owner_key": owner_key,
                    "url": f"/shop/{slug}",
                    "full_url": f"http://{host}/shop/{slug}",
                },
            )
            return

        if path.startswith("/api/shops/") and path.endswith("/chat"):
            slug = path.split("/")[3] if len(path.split("/")) > 3 else ""
            shop = fetch_shop(slug)
            if not shop:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "shop not found"})
                return
            payload = parse_json_body(self)
            message = str(payload.get("message", "")).strip()
            if not message:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": "message is required"})
                return
            reply = generate_response(shop, message)
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO chat_logs (id, shop_slug, user_message, bot_reply, created_at) VALUES (?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), slug, message, reply, utc_now()),
                )
                conn.commit()
            self.send_json(HTTPStatus.OK, {"reply": reply})
            return

        self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_PUT(self):  # noqa: N802
        path = urlparse(self.path).path
        if path.startswith("/api/shops/"):
            slug = self.parse_shop_slug("/api/shops/")
            if not slug:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "shop not found"})
                return
            shop = fetch_shop(slug)
            if not shop:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "shop not found"})
                return
            owner_key = self.headers.get("X-Owner-Key", "")
            if owner_key != shop["owner_key"]:
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "owner key invalid"})
                return
            payload = parse_json_body(self)
            name = str(payload.get("name", shop["name"])).strip() or shop["name"]
            config = {
                "rules": payload.get("rules", shop["config"].get("rules", [])),
                "timings": payload.get("timings", shop["config"].get("timings", "")),
                "products": payload.get("products", shop["config"].get("products", [])),
                "qna": payload.get("qna", shop["config"].get("qna", [])),
                "contact": payload.get("contact", shop["config"].get("contact", "")),
            }
            now = utc_now()
            with get_db() as conn:
                conn.execute(
                    "UPDATE shops SET name = ?, config_json = ?, updated_at = ? WHERE slug = ?",
                    (name, json.dumps(config), now, slug),
                )
                conn.commit()
            updated = fetch_shop(slug)
            self.send_json(HTTPStatus.OK, safe_shop_payload(updated))
            return
        self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_DELETE(self):  # noqa: N802
        path = urlparse(self.path).path
        if path.startswith("/api/shops/"):
            slug = self.parse_shop_slug("/api/shops/")
            if not slug:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "shop not found"})
                return
            shop = fetch_shop(slug)
            if not shop:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "shop not found"})
                return
            owner_key = self.headers.get("X-Owner-Key", "")
            if owner_key != shop["owner_key"]:
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "owner key invalid"})
                return
            with get_db() as conn:
                conn.execute("DELETE FROM chat_logs WHERE shop_slug = ?", (slug,))
                conn.execute("DELETE FROM shops WHERE slug = ?", (slug,))
                conn.commit()
            self.send_json(HTTPStatus.OK, {"deleted": True, "slug": slug})
            return
        self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})


def run() -> None:
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), ShopAIHandler)
    print(f"Shop AI server running on http://localhost:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    run()
