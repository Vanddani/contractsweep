from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import secrets
import sqlite3
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable

import click
from stripe import SignatureVerificationError, Webhook
from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.middleware.proxy_fix import ProxyFix

from emailer import send_email
from sam_client import SamApiError, fetch_opportunities
from scoring import score_label, score_opportunity
from security_utils import csv_safe, safe_http_url, safe_local_url

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
LOGGER = logging.getLogger("contractsweep")


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


DEMO_MODE = truthy(os.getenv("DEMO_MODE", "true"))
SECRET_KEY_VALUE = os.getenv("SECRET_KEY", "").strip()
ADMIN_TOKEN_VALUE = os.getenv("ADMIN_TOKEN", "").strip()
if not DEMO_MODE and not SECRET_KEY_VALUE:
    raise RuntimeError("SECRET_KEY is required when DEMO_MODE=false")
if not DEMO_MODE and not ADMIN_TOKEN_VALUE:
    raise RuntimeError("ADMIN_TOKEN is required when DEMO_MODE=false")
SECRET_KEY_VALUE = SECRET_KEY_VALUE or "contractsweep-development-only-secret"
ADMIN_TOKEN_VALUE = ADMIN_TOKEN_VALUE or "change-me"


app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # type: ignore[method-assign]
app.config.update(
    SECRET_KEY=SECRET_KEY_VALUE,
    DATABASE_PATH=os.getenv("DATABASE_PATH") or str(ROOT / "data" / "contractsweep.db"),
    BRAND_NAME=os.getenv("BRAND_NAME", "ContractSweep"),
    BASE_URL=os.getenv("BASE_URL", "http://localhost:5000").rstrip("/"),
    ADMIN_TOKEN=ADMIN_TOKEN_VALUE,
    TASK_TOKEN=os.getenv("TASK_TOKEN", ""),
    ENABLE_PUBLIC_DEMO=truthy(os.getenv("ENABLE_PUBLIC_DEMO", "true")),
    DEMO_MODE=DEMO_MODE,
    STRIPE_PAYMENT_LINK=os.getenv("STRIPE_PAYMENT_LINK", "#request-access"),
    STRIPE_WEBHOOK_SECRET=os.getenv("STRIPE_WEBHOOK_SECRET", ""),
    STRIPE_PAYMENT_LINK_ID=os.getenv("STRIPE_PAYMENT_LINK_ID", ""),
    RESEND_API_KEY=os.getenv("RESEND_API_KEY", ""),
    EMAIL_FROM=os.getenv("EMAIL_FROM", "ContractSweep <alerts@example.com>"),
    SUPPORT_EMAIL=os.getenv("SUPPORT_EMAIL", "support@example.com"),
    FOUNDING_PRICE=int(os.getenv("FOUNDING_PRICE", "79")),
    DEFAULT_MIN_SCORE=int(os.getenv("DEFAULT_MIN_SCORE", "50")),
    DIGEST_MAX_ITEMS=int(os.getenv("DIGEST_MAX_ITEMS", "12")),
    SESSION_COOKIE_NAME="contractsweep_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=truthy(os.getenv("SESSION_COOKIE_SECURE", "false")),
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
)

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PIPELINE_STAGES = ("watching", "qualify", "bid", "won", "lost", "dismissed")

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS opportunities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    notice_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    solicitation_number TEXT,
    agency TEXT,
    office TEXT,
    posted_date TEXT,
    response_deadline TEXT,
    naics_code TEXT,
    classification_code TEXT,
    state TEXT,
    city TEXT,
    set_aside_code TEXT,
    set_aside_description TEXT,
    notice_type TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    description_url TEXT,
    source_url TEXT,
    resource_links TEXT,
    point_of_contact TEXT,
    source TEXT NOT NULL DEFAULT 'SAM.gov',
    raw_json TEXT,
    relevance_score INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_opportunities_score ON opportunities(relevance_score DESC);
CREATE INDEX IF NOT EXISTS idx_opportunities_state ON opportunities(state);
CREATE INDEX IF NOT EXISTS idx_opportunities_deadline ON opportunities(response_deadline);
CREATE INDEX IF NOT EXISTS idx_opportunities_posted ON opportunities(posted_date DESC);

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    company TEXT,
    states TEXT,
    source TEXT NOT NULL DEFAULT 'website',
    status TEXT NOT NULL DEFAULT 'new',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS subscribers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    company TEXT,
    states TEXT,
    set_asides TEXT,
    min_score INTEGER NOT NULL DEFAULT 50,
    status TEXT NOT NULL DEFAULT 'active',
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    is_demo INTEGER NOT NULL DEFAULT 0,
    last_digest_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pipeline (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL,
    opportunity_id INTEGER NOT NULL,
    stage TEXT NOT NULL DEFAULT 'watching',
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(subscriber_id, opportunity_id),
    FOREIGN KEY(subscriber_id) REFERENCES subscribers(id) ON DELETE CASCADE,
    FOREIGN KEY(opportunity_id) REFERENCES opportunities(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS magic_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_id TEXT NOT NULL UNIQUE,
    subscriber_id INTEGER NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(subscriber_id) REFERENCES subscribers(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_magic_tokens_lookup
    ON magic_tokens(token_id, subscriber_id, used_at, expires_at);

CREATE TABLE IF NOT EXISTS task_locks (
    name TEXT PRIMARY KEY,
    acquired_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        path = Path(app.config["DATABASE_PATH"])
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path, timeout=30, detect_types=sqlite3.PARSE_DECLTYPES)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=30000")
        g.db = db
    return g.db


@app.teardown_appcontext
def close_db(_error: BaseException | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = get_db()
    db.executescript(SCHEMA)
    db.commit()


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


class TaskBusyError(RuntimeError):
    pass


def acquire_task_lock(name: str, *, ttl_minutes: int) -> None:
    db = get_db()
    db.execute(
        "DELETE FROM task_locks WHERE name=? AND datetime(acquired_at) < datetime('now', ?)",
        (name, f"-{max(1, ttl_minutes)} minutes"),
    )
    try:
        db.execute("INSERT INTO task_locks(name) VALUES(?)", (name,))
        db.commit()
    except sqlite3.IntegrityError as exc:
        db.rollback()
        raise TaskBusyError(f"{name} is already running") from exc


def release_task_lock(name: str) -> None:
    db = get_db()
    db.execute("DELETE FROM task_locks WHERE name=?", (name,))
    db.commit()


def serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="contractsweep-magic-login")


def absolute_url(endpoint: str, **values: Any) -> str:
    relative = url_for(endpoint, **values)
    return f"{app.config['BASE_URL']}{relative}"


def current_subscriber() -> dict[str, Any] | None:
    sid = session.get("subscriber_id")
    if not sid:
        return None
    row = get_db().execute(
        "SELECT * FROM subscribers WHERE id = ? AND status = 'active'", (sid,)
    ).fetchone()
    if row is None:
        session.pop("subscriber_id", None)
        return None
    return dict(row)


def login_required(view: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        if not current_subscriber():
            flash("Subscriber access is required.", "warning")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        supplied = request.headers.get("X-Admin-Token")
        expected = app.config["ADMIN_TOKEN"]
        if supplied and expected and secrets.compare_digest(str(supplied), str(expected)):
            session["is_admin"] = True
        if not session.get("is_admin"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def task_required(view: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        expected = str(app.config.get("TASK_TOKEN") or "")
        supplied = request.headers.get("X-Task-Token", "")
        authorization = request.headers.get("Authorization", "")
        if not supplied and authorization.lower().startswith("bearer "):
            supplied = authorization[7:].strip()
        if not expected:
            abort(503, description="Task endpoint is not configured")
        if not supplied or not secrets.compare_digest(str(supplied), expected):
            abort(401, description="Invalid task token")
        return view(*args, **kwargs)

    return wrapped


def csrf_token() -> str:
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(24)
        session["_csrf_token"] = token
    return str(token)


@app.before_request
def ensure_schema_and_csrf() -> None:
    csrf_exempt_endpoints = {"stripe_webhook", "task_sync", "task_digests"}
    if request.method == "POST" and request.endpoint not in csrf_exempt_endpoints:
        supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        expected = session.get("_csrf_token")
        if not expected or not supplied or not secrets.compare_digest(str(supplied), str(expected)):
            abort(400, description="Invalid CSRF token")


@app.after_request
def apply_security_headers(response: Response) -> Response:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    )
    if app.config["SESSION_COOKIE_SECURE"]:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    if request.path.startswith(("/dashboard", "/opportunity", "/profile", "/admin", "/auth", "/login", "/tasks")):
        response.headers["Cache-Control"] = "private, no-store"
    return response


@app.context_processor
def inject_globals() -> dict[str, Any]:
    return {
        "brand_name": app.config["BRAND_NAME"],
        "support_email": app.config["SUPPORT_EMAIL"],
        "founding_price": app.config["FOUNDING_PRICE"],
        "payment_link": app.config["STRIPE_PAYMENT_LINK"],
        "enable_public_demo": app.config["ENABLE_PUBLIC_DEMO"],
        "current_subscriber": current_subscriber(),
        "csrf_token": csrf_token,
        "current_year": date.today().year,
    }


@app.template_filter("date_display")
def date_display(value: Any) -> str:
    if not value:
        return "Not stated"
    text = str(value)[:10]
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d").date()
        return f"{parsed.strftime('%b')} {parsed.day}, {parsed.year}"
    except ValueError:
        return text


@app.template_filter("days_left")
def days_left(value: Any) -> str:
    if not value:
        return "No deadline"
    try:
        deadline = datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return "Deadline unknown"
    days = (deadline - date.today()).days
    if days < 0:
        return "Closed"
    if days == 0:
        return "Due today"
    return f"{days} day{'s' if days != 1 else ''} left"


@app.template_filter("score_label")
def score_label_filter(value: Any) -> str:
    try:
        return score_label(int(value))
    except (TypeError, ValueError):
        return "Unscored"


def seed_demo_data() -> int:
    db = get_db()
    today = date.today()
    samples = [
        ("DEMO-001", "Medical center janitorial services", "DEPARTMENT OF VETERANS AFFAIRS", "IL", "Chicago", 28, "561720", "SBA", "Total Small Business Set-Aside", "Solicitation"),
        ("DEMO-002", "Federal office custodial services", "GENERAL SERVICES ADMINISTRATION", "WI", "Milwaukee", 19, "561720", "8A", "8(a) Set-Aside", "Combined Synopsis/Solicitation"),
        ("DEMO-003", "Barracks turnover and deep cleaning", "DEPARTMENT OF THE ARMY", "KS", "Fort Riley", 11, "561720", "SBA", "Total Small Business Set-Aside", "Solicitation"),
        ("DEMO-004", "Airport terminal floor care and window cleaning", "DEPARTMENT OF TRANSPORTATION", "TX", "Dallas", 35, "561790", "WOSB", "Women-Owned Small Business Set-Aside", "Pre-Solicitation"),
        ("DEMO-005", "Administrative building housekeeping services", "DEPARTMENT OF AGRICULTURE", "IN", "Indianapolis", 22, "561720", "", "", "Solicitation"),
        ("DEMO-006", "Facilities support services for research campus", "DEPARTMENT OF ENERGY", "NM", "Albuquerque", 42, "561210", "SBA", "Total Small Business Set-Aside", "Sources Sought"),
        ("DEMO-007", "Courthouse custodial and restroom sanitation", "U.S. COURTS", "MO", "St. Louis", 14, "561720", "SDVOSBC", "SDVOSB Set-Aside", "Solicitation"),
        ("DEMO-008", "Custodial supplies and paper products", "DEPARTMENT OF THE AIR FORCE", "OH", "Dayton", 26, "423850", "SBA", "Total Small Business Set-Aside", "Solicitation"),
        ("DEMO-009", "Clinic disinfection and recurring cleaning services", "DEPARTMENT OF HEALTH AND HUMAN SERVICES", "MN", "Minneapolis", 7, "561720", "EDWOSB", "EDWOSB Set-Aside", "Combined Synopsis/Solicitation"),
        ("DEMO-010", "Carpet cleaning for federal training center", "DEPARTMENT OF HOMELAND SECURITY", "GA", "Atlanta", 31, "561740", "SBA", "Total Small Business Set-Aside", "Solicitation"),
        ("DEMO-011", "Exterior building washing and related services", "DEPARTMENT OF THE INTERIOR", "CO", "Denver", 18, "561790", "HZC", "HUBZone Set-Aside", "Solicitation"),
        ("DEMO-012", "Janitorial services market research notice", "SMALL BUSINESS ADMINISTRATION", "DC", "Washington", 16, "561720", "", "", "Sources Sought"),
    ]
    count = 0
    for idx, (notice_id, title, agency, state, city, due_in, naics, set_code, set_desc, notice_type) in enumerate(samples, start=1):
        item = {
            "notice_id": notice_id,
            "title": title,
            "solicitation_number": f"DEMO-26-{idx:03d}",
            "agency": agency,
            "office": "Demo contracting office",
            "posted_date": (today - timedelta(days=(idx % 9) + 1)).isoformat(),
            "response_deadline": (today + timedelta(days=due_in)).isoformat(),
            "naics_code": naics,
            "classification_code": "S201",
            "state": state,
            "city": city,
            "set_aside_code": set_code,
            "set_aside_description": set_desc,
            "notice_type": notice_type,
            "active": 1,
            "description_url": "",
            "source_url": "https://sam.gov/content/opportunities",
            "resource_links": "[]",
            "point_of_contact": json.dumps([{"type": "primary", "fullName": "Demo Contract Specialist", "email": "demo@example.gov"}]),
            "source": "DEMO",
            "raw_json": "{}",
        }
        item["relevance_score"], _ = score_opportunity(item)
        upsert_opportunity(db, item)
        count += 1
    ensure_demo_subscriber(db)
    db.commit()
    return count


def ensure_demo_subscriber(db: sqlite3.Connection | None = None) -> int:
    db = db or get_db()
    db.execute(
        """
        INSERT INTO subscribers(email, company, states, min_score, status, is_demo)
        VALUES(?, ?, ?, ?, 'active', 1)
        ON CONFLICT(email) DO UPDATE SET status='active', is_demo=1, updated_at=CURRENT_TIMESTAMP
        """,
        ("demo@contractsweep.local", "Demo Cleaning Co.", "IL,WI,IN", 45),
    )
    db.commit()
    row = db.execute("SELECT id FROM subscribers WHERE email = ?", ("demo@contractsweep.local",)).fetchone()
    return int(row["id"])


def upsert_opportunity(db: sqlite3.Connection, item: dict[str, Any]) -> None:
    columns = [
        "notice_id", "title", "solicitation_number", "agency", "office", "posted_date",
        "response_deadline", "naics_code", "classification_code", "state", "city",
        "set_aside_code", "set_aside_description", "notice_type", "active",
        "description_url", "source_url", "resource_links", "point_of_contact", "source",
        "raw_json", "relevance_score",
    ]
    values = [item.get(column) for column in columns]
    update_clause = ", ".join(f"{column}=excluded.{column}" for column in columns if column != "notice_id")
    placeholders = ", ".join("?" for _ in columns)
    db.execute(
        f"""
        INSERT INTO opportunities({', '.join(columns)}) VALUES({placeholders})
        ON CONFLICT(notice_id) DO UPDATE SET {update_clause}, updated_at=CURRENT_TIMESTAMP
        """,
        values,
    )


def sync_sam_data() -> tuple[int, int]:
    acquire_task_lock("sam-sync", ttl_minutes=20)
    try:
        api_key = os.getenv("SAM_API_KEY", "").strip()
        codes = [
            code.strip()
            for code in os.getenv(
                "SAM_NAICS_CODES", "561720,561210,561790,561740"
            ).split(",")
            if code.strip()
        ]
        lookback = int(os.getenv("SAM_LOOKBACK_DAYS", "120"))
        records = fetch_opportunities(api_key, lookback_days=lookback, naics_codes=codes)
        db = get_db()
        if truthy(os.getenv("DELETE_DEMO_ON_SYNC", "true")) and records:
            db.execute("DELETE FROM opportunities WHERE source = 'DEMO'")
        if codes:
            placeholders = ", ".join("?" for _ in codes)
            cutoff = (date.today() - timedelta(days=lookback)).isoformat()
            db.execute(
                f"""
                UPDATE opportunities
                SET active = 0, updated_at = CURRENT_TIMESTAMP
                WHERE source = 'SAM.gov'
                  AND naics_code IN ({placeholders})
                  AND (posted_date = '' OR date(posted_date) >= date(?))
                """,
                [*codes, cutoff],
            )
        for item in records:
            upsert_opportunity(db, item)
        db.commit()
        return len(records), len(codes)
    except Exception:
        get_db().rollback()
        raise
    finally:
        release_task_lock("sam-sync")


def send_magic_link(email: str, subscriber_id: int) -> tuple[bool, str]:
    token_id = secrets.token_urlsafe(24)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    db = get_db()
    db.execute(
        "UPDATE magic_tokens SET used_at=CURRENT_TIMESTAMP WHERE subscriber_id=? AND used_at IS NULL",
        (subscriber_id,),
    )
    db.execute(
        "DELETE FROM magic_tokens WHERE datetime(expires_at) < datetime('now', '-7 days')",
    )
    db.execute(
        "INSERT INTO magic_tokens(token_id, subscriber_id, expires_at) VALUES(?, ?, ?)",
        (token_id, subscriber_id, expires_at),
    )
    db.commit()
    token = serializer().dumps({"sid": subscriber_id, "email": email.lower(), "jti": token_id})
    link = absolute_url("magic_login", token=token)
    html = render_template("email_magic_link.html", magic_link=link, email=email)
    sent = send_email(
        api_key=app.config["RESEND_API_KEY"],
        sender=app.config["EMAIL_FROM"],
        recipients=email,
        subject=f"Your {app.config['BRAND_NAME']} sign-in link",
        html=html,
    )
    return sent, link


def query_opportunities(subscriber_id: int, args: Any, *, all_rows: bool = False) -> tuple[list[sqlite3.Row], int]:
    q = str(args.get("q", "")).strip()
    state = str(args.get("state", "")).strip().upper()
    set_aside = str(args.get("set_aside", "")).strip()
    stage = str(args.get("stage", "")).strip()
    min_score_raw = str(args.get("min_score", "")).strip()
    deadline_days_raw = str(args.get("deadline_days", "")).strip()
    active_only = str(args.get("active", "1")) != "0"

    subscriber = get_db().execute("SELECT * FROM subscribers WHERE id = ?", (subscriber_id,)).fetchone()
    default_min = subscriber["min_score"] if subscriber else app.config["DEFAULT_MIN_SCORE"]
    try:
        min_score = max(0, min(100, int(min_score_raw or default_min)))
    except ValueError:
        min_score = int(default_min)

    where = ["o.relevance_score >= ?"]
    params: list[Any] = [min_score]
    if subscriber and subscriber["is_demo"]:
        where.append("o.source = 'DEMO'")
    else:
        where.append("o.source <> 'DEMO'")
    if active_only:
        where.append("o.active = 1")
        where.append("(o.response_deadline IS NULL OR o.response_deadline = '' OR date(o.response_deadline) >= date('now'))")
    if q:
        where.append("(o.title LIKE ? OR o.agency LIKE ? OR o.solicitation_number LIKE ? OR o.city LIKE ?)")
        wildcard = f"%{q}%"
        params.extend([wildcard, wildcard, wildcard, wildcard])
    if state:
        where.append("o.state = ?")
        params.append(state)
    if set_aside:
        where.append("o.set_aside_code = ?")
        params.append(set_aside)
    if stage:
        if stage == "untracked":
            where.append("p.stage IS NULL")
        else:
            where.append("p.stage = ?")
            params.append(stage)
    if deadline_days_raw:
        try:
            deadline_days = max(1, min(365, int(deadline_days_raw)))
            where.append("date(o.response_deadline) <= date('now', ?)")
            params.append(f"+{deadline_days} days")
        except ValueError:
            pass

    join = "LEFT JOIN pipeline p ON p.opportunity_id = o.id AND p.subscriber_id = ?"
    base_params = [subscriber_id, *params]
    where_sql = " AND ".join(where)
    total = get_db().execute(
        f"SELECT COUNT(*) AS count FROM opportunities o {join} WHERE {where_sql}", base_params
    ).fetchone()["count"]

    pagination_sql = ""
    if not all_rows:
        try:
            page = max(1, int(args.get("page", 1)))
        except (TypeError, ValueError):
            page = 1
        page_size = 25
        pagination_sql = " LIMIT ? OFFSET ?"
        base_params.extend([page_size, (page - 1) * page_size])

    rows = get_db().execute(
        f"""
        SELECT o.*, p.stage AS pipeline_stage, p.notes AS pipeline_notes
        FROM opportunities o
        {join}
        WHERE {where_sql}
        ORDER BY o.relevance_score DESC,
                 CASE WHEN o.response_deadline IS NULL OR o.response_deadline = '' THEN 1 ELSE 0 END,
                 date(o.response_deadline) ASC,
                 date(o.posted_date) DESC
        {pagination_sql}
        """,
        base_params,
    ).fetchall()
    return rows, int(total)


@app.route("/")
def index() -> str:
    if app.config["DEMO_MODE"]:
        seed_demo_data()
    db = get_db()
    stats = db.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN relevance_score >= 75 THEN 1 ELSE 0 END) AS high_count,
               COUNT(DISTINCT CASE WHEN state <> '' THEN state END) AS states,
               MAX(updated_at) AS latest
        FROM opportunities
        """
    ).fetchone()
    return render_template("index.html", stats=stats)


@app.route("/health")
def health() -> Response:
    db = get_db()
    db.execute("SELECT 1").fetchone()
    return jsonify({"status": "ok", "service": app.config["BRAND_NAME"]})


@app.route("/request-access", methods=["POST"])
def request_access() -> Response:
    email = request.form.get("email", "").strip().lower()[:320]
    company = request.form.get("company", "").strip()[:200]
    states = request.form.get("states", "").strip().upper()[:300]
    if not EMAIL_RE.match(email):
        flash("Enter a valid business email address.", "error")
        return redirect(url_for("index", _anchor="request-access"))
    db = get_db()
    db.execute(
        """
        INSERT INTO leads(email, company, states, source) VALUES(?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET company=excluded.company, states=excluded.states,
            status='new', updated_at=CURRENT_TIMESTAMP
        """,
        (email, company, states, request.form.get("source", "website").strip()[:100]),
    )
    db.commit()
    flash("Request recorded. The next step is a short fit check and paid founding access.", "success")
    return redirect(url_for("index", _anchor="request-access"))


@app.route("/demo")
def demo() -> Response:
    if not app.config["ENABLE_PUBLIC_DEMO"]:
        abort(404)
    seed_demo_data()
    session.clear()
    session["subscriber_id"] = ensure_demo_subscriber()
    session.permanent = True
    return redirect(url_for("dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login() -> str | Response:
    magic_link = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()[:320]
        row = None
        if EMAIL_RE.match(email):
            row = get_db().execute(
                "SELECT id, email FROM subscribers WHERE email = ? AND status = 'active'", (email,)
            ).fetchone()
        if row:
            sent, link = send_magic_link(row["email"], int(row["id"]))
            if not sent and app.config["DEMO_MODE"]:
                magic_link = link
                flash("Email is not configured, so a local test link is shown below.", "warning")
            elif not sent:
                LOGGER.error("Magic-link delivery failed for subscriber id=%s", row["id"])
        if magic_link is None:
            flash("If an active subscription exists for that address, a sign-in link will be sent.", "success")
    return render_template("login.html", magic_link=magic_link)


@app.route("/auth/<token>")
def magic_login(token: str) -> Response:
    try:
        payload = serializer().loads(token, max_age=1800)
    except SignatureExpired:
        flash("That sign-in link expired. Request a new one.", "warning")
        return redirect(url_for("login"))
    except BadSignature:
        abort(400, description="Invalid sign-in token")
    db = get_db()
    row = db.execute(
        "SELECT id, email FROM subscribers WHERE id = ? AND email = ? AND status = 'active'",
        (payload.get("sid"), payload.get("email")),
    ).fetchone()
    token_row = db.execute(
        """
        SELECT id FROM magic_tokens
        WHERE token_id = ? AND subscriber_id = ? AND used_at IS NULL
          AND datetime(expires_at) >= datetime('now')
        """,
        (payload.get("jti"), payload.get("sid")),
    ).fetchone()
    if not row or not token_row:
        abort(403, description="Sign-in link is invalid, expired, or already used")
    updated = db.execute(
        "UPDATE magic_tokens SET used_at=CURRENT_TIMESTAMP WHERE id=? AND used_at IS NULL",
        (token_row["id"],),
    )
    db.commit()
    if updated.rowcount != 1:
        abort(403, description="Sign-in link has already been used")
    session.clear()
    session["subscriber_id"] = int(row["id"])
    session.permanent = True
    flash("Signed in.", "success")
    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout() -> Response:
    session.clear()
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard() -> str:
    subscriber = current_subscriber()
    assert subscriber is not None
    rows, total = query_opportunities(int(subscriber["id"]), request.args)
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    pages = max(1, (total + 24) // 25)
    db = get_db()
    source_clause = " AND source = 'DEMO'" if subscriber["is_demo"] else " AND source <> 'DEMO'"
    states = db.execute(
        f"SELECT DISTINCT state FROM opportunities WHERE state <> ''{source_clause} ORDER BY state"
    ).fetchall()
    set_asides = db.execute(
        f"SELECT DISTINCT set_aside_code, set_aside_description FROM opportunities "
        f"WHERE set_aside_code <> ''{source_clause} ORDER BY set_aside_description"
    ).fetchall()
    source_counts = db.execute(
        f"SELECT source, COUNT(*) AS count FROM opportunities WHERE 1=1{source_clause} GROUP BY source"
    ).fetchall()
    return render_template(
        "dashboard.html",
        opportunities=rows,
        total=total,
        page=page,
        pages=pages,
        states=states,
        set_asides=set_asides,
        source_counts=source_counts,
        pipeline_stages=PIPELINE_STAGES,
        filter_args={k: v for k, v in request.args.to_dict().items() if k != "page"},
    )


@app.route("/opportunity/<int:opportunity_id>")
@login_required
def opportunity_detail(opportunity_id: int) -> str:
    subscriber = current_subscriber()
    assert subscriber is not None
    row = get_db().execute(
        """
        SELECT o.*, p.stage AS pipeline_stage, p.notes AS pipeline_notes
        FROM opportunities o
        LEFT JOIN pipeline p ON p.opportunity_id = o.id AND p.subscriber_id = ?
        WHERE o.id = ?
          AND ((? = 1 AND o.source = 'DEMO') OR (? = 0 AND o.source <> 'DEMO'))
        """,
        (subscriber["id"], opportunity_id, int(subscriber["is_demo"]), int(subscriber["is_demo"])),
    ).fetchone()
    if not row:
        abort(404)
    item = dict(row)
    item["source_url"] = safe_http_url(item.get("source_url"))
    try:
        raw_resources = json.loads(item.get("resource_links") or "[]")
    except json.JSONDecodeError:
        raw_resources = []
    resources = (
        [safe_http_url(link) for link in raw_resources if safe_http_url(link)]
        if isinstance(raw_resources, list)
        else []
    )
    try:
        raw_contacts = json.loads(item.get("point_of_contact") or "[]")
    except json.JSONDecodeError:
        raw_contacts = []
    contacts = [contact for contact in raw_contacts if isinstance(contact, dict)] if isinstance(raw_contacts, list) else []
    _, reasons = score_opportunity(item)
    return render_template(
        "opportunity.html",
        opportunity=item,
        resources=resources,
        contacts=contacts,
        score_reasons=reasons,
        pipeline_stages=PIPELINE_STAGES,
    )


@app.route("/opportunity/<int:opportunity_id>/pipeline", methods=["POST"])
@login_required
def update_pipeline(opportunity_id: int) -> Response:
    subscriber = current_subscriber()
    assert subscriber is not None
    if subscriber["is_demo"]:
        flash("The public demo is read-only. Subscriber accounts can save pipeline decisions.", "warning")
        return redirect(url_for("opportunity_detail", opportunity_id=opportunity_id))
    stage = request.form.get("stage", "watching").strip().lower()
    notes = request.form.get("notes", "").strip()[:4000]
    if stage not in PIPELINE_STAGES:
        abort(400, description="Invalid pipeline stage")
    exists = get_db().execute(
        """
        SELECT id FROM opportunities
        WHERE id = ?
          AND ((? = 1 AND source = 'DEMO') OR (? = 0 AND source <> 'DEMO'))
        """,
        (opportunity_id, int(subscriber["is_demo"]), int(subscriber["is_demo"])),
    ).fetchone()
    if not exists:
        abort(404)
    get_db().execute(
        """
        INSERT INTO pipeline(subscriber_id, opportunity_id, stage, notes)
        VALUES(?, ?, ?, ?)
        ON CONFLICT(subscriber_id, opportunity_id)
        DO UPDATE SET stage=excluded.stage, notes=excluded.notes, updated_at=CURRENT_TIMESTAMP
        """,
        (subscriber["id"], opportunity_id, stage, notes),
    )
    get_db().commit()
    flash("Pipeline status updated.", "success")
    return redirect(safe_local_url(request.form.get("next"), url_for("opportunity_detail", opportunity_id=opportunity_id)))


@app.route("/calculator")
def calculator() -> str:
    return render_template("calculator.html")


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile() -> str | Response:
    subscriber = current_subscriber()
    assert subscriber is not None
    if request.method == "POST":
        if subscriber["is_demo"]:
            flash("The public demo profile is read-only.", "warning")
            return redirect(url_for("profile"))
        company = request.form.get("company", "").strip()[:200]
        states = request.form.get("states", "").strip().upper()[:300]
        set_asides = request.form.get("set_asides", "").strip().upper()[:300]
        try:
            min_score = max(0, min(100, int(request.form.get("min_score", 50))))
        except ValueError:
            min_score = 50
        get_db().execute(
            "UPDATE subscribers SET company=?, states=?, set_asides=?, min_score=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (company, states, set_asides, min_score, subscriber["id"]),
        )
        get_db().commit()
        flash("Alert profile saved.", "success")
        return redirect(url_for("profile"))
    return render_template("profile.html", subscriber=subscriber)


@app.route("/opportunities.csv")
@login_required
def export_opportunities() -> Response:
    subscriber = current_subscriber()
    assert subscriber is not None
    rows, _ = query_opportunities(int(subscriber["id"]), request.args, all_rows=True)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Score", "Title", "Agency", "State", "City", "Posted", "Deadline", "Days left",
        "NAICS", "Set-aside", "Notice type", "Solicitation number", "Pipeline stage", "Source URL",
    ])
    for row in rows:
        writer.writerow([
            csv_safe(value)
            for value in [
                row["relevance_score"], row["title"], row["agency"], row["state"], row["city"],
                row["posted_date"], row["response_deadline"], days_left(row["response_deadline"]),
                row["naics_code"], row["set_aside_description"], row["notice_type"],
                row["solicitation_number"], row["pipeline_stage"] or "", row["source_url"],
            ]
        ])
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=contractsweep-{date.today().isoformat()}.csv"},
    )


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login() -> str | Response:
    if request.method == "POST":
        supplied = request.form.get("token", "")
        if secrets.compare_digest(str(supplied), str(app.config["ADMIN_TOKEN"])):
            session.clear()
            session["is_admin"] = True
            session.permanent = True
            return redirect(url_for("admin"))
        flash("Invalid admin token.", "error")
    return render_template("admin_login.html")


@app.route("/admin")
@admin_required
def admin() -> str:
    db = get_db()
    leads = db.execute("SELECT * FROM leads ORDER BY created_at DESC LIMIT 100").fetchall()
    subscribers = db.execute("SELECT * FROM subscribers ORDER BY created_at DESC").fetchall()
    counts = {
        "leads": db.execute("SELECT COUNT(*) AS c FROM leads").fetchone()["c"],
        "subscribers": db.execute("SELECT COUNT(*) AS c FROM subscribers WHERE status='active' AND is_demo=0").fetchone()["c"],
        "opportunities": db.execute("SELECT COUNT(*) AS c FROM opportunities WHERE source <> 'DEMO'").fetchone()["c"],
        "high": db.execute(
            "SELECT COUNT(*) AS c FROM opportunities WHERE source <> 'DEMO' AND relevance_score >= 75"
        ).fetchone()["c"],
    }
    return render_template("admin.html", leads=leads, subscribers=subscribers, counts=counts)


@app.route("/admin/subscribers", methods=["POST"])
@admin_required
def admin_create_subscriber() -> Response:
    email = request.form.get("email", "").strip().lower()[:320]
    company = request.form.get("company", "").strip()[:200]
    states = request.form.get("states", "").strip().upper()[:300]
    if not EMAIL_RE.match(email):
        flash("Valid subscriber email required.", "error")
        return redirect(url_for("admin"))
    get_db().execute(
        """
        INSERT INTO subscribers(email, company, states, min_score, status)
        VALUES(?, ?, ?, ?, 'active')
        ON CONFLICT(email) DO UPDATE SET company=excluded.company, states=excluded.states,
            status='active', is_demo=0, updated_at=CURRENT_TIMESTAMP
        """,
        (email, company, states, app.config["DEFAULT_MIN_SCORE"]),
    )
    get_db().execute("UPDATE leads SET status='converted', updated_at=CURRENT_TIMESTAMP WHERE email=?", (email,))
    get_db().commit()
    row = get_db().execute("SELECT id FROM subscribers WHERE email=?", (email,)).fetchone()
    sent, link = send_magic_link(email, int(row["id"]))
    if sent:
        flash("Subscriber activated and login link sent.", "success")
    else:
        flash(f"Subscriber activated. Email not sent; test link: {link}", "warning")
    return redirect(url_for("admin"))


@app.route("/admin/subscribers/<int:subscriber_id>/status", methods=["POST"])
@admin_required
def admin_subscriber_status(subscriber_id: int) -> Response:
    status = request.form.get("status", "inactive")
    if status not in {"active", "inactive"}:
        abort(400)
    get_db().execute(
        "UPDATE subscribers SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND is_demo=0",
        (status, subscriber_id),
    )
    get_db().commit()
    flash("Subscriber status updated.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/sync", methods=["POST"])
@admin_required
def admin_sync() -> Response:
    try:
        count, code_count = sync_sam_data()
        flash(f"Imported or refreshed {count} opportunities across {code_count} NAICS codes.", "success")
    except (SamApiError, ValueError, TaskBusyError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin"))


@app.route("/tasks/sync", methods=["POST"])
@task_required
def task_sync() -> Response:
    try:
        count, code_count = sync_sam_data()
    except SamApiError as exc:
        LOGGER.exception("Scheduled SAM.gov sync failed")
        return jsonify({"ok": False, "error": str(exc)}), 502
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503
    except TaskBusyError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    return jsonify({"ok": True, "opportunities": count, "naics_codes": code_count})


@app.route("/tasks/digests", methods=["POST"])
@task_required
def task_digests() -> Response:
    try:
        sent, skipped = send_all_digests()
    except TaskBusyError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    return jsonify({"ok": True, "sent": sent, "skipped": skipped})


@app.route("/admin/leads.csv")
@admin_required
def export_leads() -> Response:
    rows = get_db().execute("SELECT * FROM leads ORDER BY created_at DESC").fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Email", "Company", "States", "Source", "Status", "Created"])
    for row in rows:
        writer.writerow([
            csv_safe(value)
            for value in [row["email"], row["company"], row["states"], row["source"], row["status"], row["created_at"]]
        ])
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=contractsweep-leads.csv"},
    )


@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook() -> Response:
    secret = app.config["STRIPE_WEBHOOK_SECRET"]
    if not secret:
        abort(503, description="Stripe webhook is not configured")
    signature = request.headers.get("Stripe-Signature", "")
    try:
        event = Webhook.construct_event(request.get_data(), signature, secret).to_dict()
    except (ValueError, SignatureVerificationError):
        abort(400, description="Invalid Stripe webhook")

    event_type = event.get("type")
    obj = event.get("data", {}).get("object", {})
    db = get_db()
    if event_type == "checkout.session.completed":
        allowed_link = str(app.config.get("STRIPE_PAYMENT_LINK_ID") or "")
        payment_link = str(obj.get("payment_link") or "")
        mode = str(obj.get("mode") or "")
        payment_status = str(obj.get("payment_status") or "")
        if mode != "subscription" or payment_status not in {"paid", "no_payment_required"}:
            return jsonify({"received": True, "activated": False})
        if allowed_link and payment_link != allowed_link:
            return jsonify({"received": True, "activated": False})
        details = obj.get("customer_details") or {}
        email = str(details.get("email") or obj.get("customer_email") or "").strip().lower()
        if email and EMAIL_RE.match(email):
            subscription_id = obj.get("subscription")
            customer_id = obj.get("customer")
            db.execute(
                """
                INSERT INTO subscribers(email, status, stripe_customer_id, stripe_subscription_id, min_score)
                VALUES(?, 'active', ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET status='active', stripe_customer_id=excluded.stripe_customer_id,
                    stripe_subscription_id=excluded.stripe_subscription_id, is_demo=0, updated_at=CURRENT_TIMESTAMP
                """,
                (email, customer_id, subscription_id, app.config["DEFAULT_MIN_SCORE"]),
            )
            db.execute("UPDATE leads SET status='converted', updated_at=CURRENT_TIMESTAMP WHERE email=?", (email,))
            db.commit()
            row = db.execute("SELECT id FROM subscribers WHERE email=?", (email,)).fetchone()
            send_magic_link(email, int(row["id"]))
    elif event_type in {"customer.subscription.deleted", "customer.subscription.paused"}:
        subscription_id = obj.get("id")
        db.execute(
            "UPDATE subscribers SET status='inactive', updated_at=CURRENT_TIMESTAMP WHERE stripe_subscription_id=?",
            (subscription_id,),
        )
        db.commit()
    elif event_type == "customer.subscription.updated":
        subscription_id = obj.get("id")
        stripe_status = str(obj.get("status") or "")
        local_status = "active" if stripe_status in {"active", "trialing"} else "inactive"
        db.execute(
            "UPDATE subscribers SET status=?, updated_at=CURRENT_TIMESTAMP WHERE stripe_subscription_id=?",
            (local_status, subscription_id),
        )
        db.commit()
    return jsonify({"received": True})


def digest_rows_for(subscriber: sqlite3.Row) -> list[sqlite3.Row]:
    states = [state.strip().upper() for state in str(subscriber["states"] or "").split(",") if state.strip()]
    set_asides = [code.strip().upper() for code in str(subscriber["set_asides"] or "").split(",") if code.strip()]
    where = [
        "active = 1",
        "source <> 'DEMO'",
        "relevance_score >= ?",
        "(response_deadline IS NULL OR response_deadline = '' OR date(response_deadline) >= date('now'))",
    ]
    params: list[Any] = [subscriber["min_score"]]
    if states:
        where.append(f"state IN ({', '.join('?' for _ in states)})")
        params.extend(states)
    if set_asides:
        where.append(f"set_aside_code IN ({', '.join('?' for _ in set_asides)})")
        params.extend(set_asides)
    if subscriber["last_digest_at"]:
        where.append("datetime(created_at) > datetime(?)")
        params.append(subscriber["last_digest_at"])
    params.append(app.config["DIGEST_MAX_ITEMS"])
    return get_db().execute(
        f"""
        SELECT * FROM opportunities WHERE {' AND '.join(where)}
        ORDER BY relevance_score DESC, date(response_deadline) ASC
        LIMIT ?
        """,
        params,
    ).fetchall()


def send_all_digests() -> tuple[int, int]:
    acquire_task_lock("email-digests", ttl_minutes=60)
    try:
        subscribers = get_db().execute(
            "SELECT * FROM subscribers WHERE status='active' AND is_demo=0 ORDER BY id"
        ).fetchall()
        sent_count = 0
        skipped = 0
        for subscriber in subscribers:
            rows = digest_rows_for(subscriber)
            if not rows:
                skipped += 1
                continue
            html = render_template(
                "email_digest.html",
                subscriber=subscriber,
                opportunities=rows,
                base_url=app.config["BASE_URL"],
            )
            sent = send_email(
                api_key=app.config["RESEND_API_KEY"],
                sender=app.config["EMAIL_FROM"],
                recipients=subscriber["email"],
                subject=f"{len(rows)} contract matches from {app.config['BRAND_NAME']}",
                html=html,
            )
            if sent:
                sent_count += 1
                get_db().execute(
                    "UPDATE subscribers SET last_digest_at=CURRENT_TIMESTAMP WHERE id=?",
                    (subscriber["id"],),
                )
                get_db().commit()
            else:
                skipped += 1
        return sent_count, skipped
    finally:
        release_task_lock("email-digests")


@app.cli.command("init-db")
def init_db_command() -> None:
    init_db()
    click.echo(f"Initialized {app.config['DATABASE_PATH']}")


@app.cli.command("seed-demo")
def seed_demo_command() -> None:
    count = seed_demo_data()
    click.echo(f"Seeded {count} demo opportunities")


@app.cli.command("sync-sam")
def sync_sam_command() -> None:
    try:
        count, code_count = sync_sam_data()
    except (SamApiError, ValueError, TaskBusyError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Imported or refreshed {count} opportunities across {code_count} NAICS codes")


@app.cli.command("send-digests")
def send_digests_command() -> None:
    try:
        sent, skipped = send_all_digests()
    except TaskBusyError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Sent {sent} digests; skipped {skipped}")


@app.cli.command("create-subscriber")
@click.option("--email", required=True)
@click.option("--company", default="")
@click.option("--states", default="")
def create_subscriber_command(email: str, company: str, states: str) -> None:
    if not EMAIL_RE.match(email):
        raise click.ClickException("Invalid email address")
    db = get_db()
    db.execute(
        """
        INSERT INTO subscribers(email, company, states, min_score, status)
        VALUES(?, ?, ?, ?, 'active')
        ON CONFLICT(email) DO UPDATE SET company=excluded.company, states=excluded.states,
            status='active', is_demo=0, updated_at=CURRENT_TIMESTAMP
        """,
        (email.lower(), company, states.upper(), app.config["DEFAULT_MIN_SCORE"]),
    )
    db.commit()
    click.echo(f"Activated {email.lower()}")


with app.app_context():
    init_db()
    if app.config["DEMO_MODE"]:
        seed_demo_data()


if __name__ == "__main__":
    app.run(debug=app.config["DEMO_MODE"], host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
