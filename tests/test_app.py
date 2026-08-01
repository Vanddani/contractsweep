import pytest

import app as app_module


@pytest.fixture()
def client(tmp_path):
    app_module.app.config.update(
        TESTING=True,
        DATABASE_PATH=str(tmp_path / "test.db"),
        SECRET_KEY="test-secret",
        ENABLE_PUBLIC_DEMO=True,
        DEMO_MODE=True,
    )
    with app_module.app.app_context():
        app_module.init_db()
        app_module.seed_demo_data()
    with app_module.app.test_client() as client:
        yield client


def test_index_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Spend less time searching" in response.data


def test_public_demo_opens_dashboard(client):
    response = client.get("/demo", follow_redirects=True)
    assert response.status_code == 200
    assert b"Contract opportunity queue" in response.data
    assert b"Medical center janitorial services" in response.data


def test_calculator_renders(client):
    response = client.get("/calculator")
    assert response.status_code == 200
    assert b"bid-floor calculator" in response.data


def test_csv_export_after_demo_login(client):
    client.get("/demo")
    response = client.get("/opportunities.csv")
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert b"Medical center janitorial services" in response.data


def test_public_demo_cannot_see_live_records(client):
    with app_module.app.app_context():
        db = app_module.get_db()
        live = {
            "notice_id": "LIVE-PRIVATE-001",
            "title": "Private live subscriber record",
            "source": "SAM.gov",
            "active": 1,
            "relevance_score": 99,
        }
        app_module.upsert_opportunity(db, live)
        db.commit()
        live_id = db.execute(
            "SELECT id FROM opportunities WHERE notice_id='LIVE-PRIVATE-001'"
        ).fetchone()["id"]

    response = client.get("/demo", follow_redirects=True)
    assert b"Private live subscriber record" not in response.data
    detail = client.get(f"/opportunity/{live_id}")
    assert detail.status_code == 404
    export = client.get("/opportunities.csv")
    assert b"Private live subscriber record" not in export.data



def test_live_subscriber_cannot_see_demo_records(client):
    with app_module.app.app_context():
        db = app_module.get_db()
        db.execute(
            """
            INSERT INTO subscribers(email, company, status, is_demo, min_score)
            VALUES('live@example.com', 'Live Cleaner', 'active', 0, 0)
            """
        )
        live = {
            "notice_id": "LIVE-VISIBLE-001",
            "title": "Real live janitorial opportunity",
            "source": "SAM.gov",
            "active": 1,
            "relevance_score": 99,
        }
        app_module.upsert_opportunity(db, live)
        db.commit()
        subscriber_id = db.execute(
            "SELECT id FROM subscribers WHERE email='live@example.com'"
        ).fetchone()["id"]
        demo_id = db.execute(
            "SELECT id FROM opportunities WHERE source='DEMO' LIMIT 1"
        ).fetchone()["id"]

    with client.session_transaction() as sess:
        sess.clear()
        sess["subscriber_id"] = subscriber_id
    response = client.get("/dashboard?min_score=0")
    assert response.status_code == 200
    assert b"Real live janitorial opportunity" in response.data
    assert b"Medical center janitorial services" not in response.data
    assert client.get(f"/opportunity/{demo_id}").status_code == 404
    export = client.get("/opportunities.csv?min_score=0")
    assert b"Real live janitorial opportunity" in export.data
    assert b"Medical center janitorial services" not in export.data

def test_task_endpoint_requires_token(client, monkeypatch):
    app_module.app.config["TASK_TOKEN"] = "task-secret"
    monkeypatch.setattr(app_module, "sync_sam_data", lambda: (7, 4))
    assert client.post("/tasks/sync").status_code == 401
    response = client.post("/tasks/sync", headers={"X-Task-Token": "task-secret"})
    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "opportunities": 7, "naics_codes": 4}


def test_magic_link_is_one_time(client):
    with app_module.app.app_context():
        row = app_module.get_db().execute(
            "SELECT id, email FROM subscribers WHERE email='demo@contractsweep.local'"
        ).fetchone()
        _, link = app_module.send_magic_link(row["email"], row["id"])
    path = link.removeprefix(app_module.app.config["BASE_URL"])
    first = client.get(path)
    assert first.status_code == 302
    second = client.get(path)
    assert second.status_code == 403


def test_security_headers_are_present(client):
    response = client.get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]


def test_legal_pages_render(client):
    for path, marker in [
        ("/terms", b"Terms of Service and Subscription Terms"),
        ("/privacy", b"Privacy Notice"),
        ("/cancellation-refunds", b"Cancellation and Refund Policy"),
        ("/disclosures", b"Government-Affiliation Disclosures"),
    ]:
        response = client.get(path)
        assert response.status_code == 200
        assert marker in response.data


def test_paid_checkout_requires_approved_legal_configuration(client, monkeypatch):
    monkeypatch.setitem(app_module.app.config, "STRIPE_PAYMENT_LINK", "https://buy.stripe.com/example")
    monkeypatch.setitem(app_module.app.config, "LEGAL_SELLER_NAME", "Example Seller, doing business as ContractSweep")
    monkeypatch.setitem(app_module.app.config, "LEGAL_MAILING_ADDRESS", "100 Main Street | Minneapolis, MN 55401 | United States")
    monkeypatch.setitem(app_module.app.config, "SUPPORT_EMAIL", "support@contractsweep.example")
    monkeypatch.setitem(app_module.app.config, "LEGAL_PAGES_APPROVED", False)
    # The context processor must keep checkout hidden until the explicit approval flag is true.
    response = client.get("/")
    assert b"Start paid access" not in response.data
    assert b"Request an invite" in response.data

    monkeypatch.setitem(app_module.app.config, "LEGAL_PAGES_APPROVED", True)
    response = client.get("/")
    assert b"Start paid access" in response.data
    assert b"charged monthly until canceled" in response.data


def test_subscriber_can_record_cancellation_request(client):
    with app_module.app.app_context():
        db = app_module.get_db()
        db.execute(
            """
            INSERT INTO subscribers(email, company, status, is_demo, min_score, stripe_subscription_id)
            VALUES('cancel@example.com', 'Cancel Test', 'active', 0, 0, 'sub_test_123')
            """
        )
        db.commit()
        subscriber_id = db.execute(
            "SELECT id FROM subscribers WHERE email='cancel@example.com'"
        ).fetchone()["id"]

    with client.session_transaction() as sess:
        sess.clear()
        sess["subscriber_id"] = subscriber_id
        sess["_csrf_token"] = "test-csrf"

    response = client.post(
        "/cancellation-refunds",
        data={
            "csrf_token": "test-csrf",
            "acknowledge": "yes",
            "reason": "No longer pursuing federal work",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Cancellation request recorded" in response.data

    with app_module.app.app_context():
        db = app_module.get_db()
        request_row = db.execute(
            "SELECT * FROM cancellation_requests WHERE subscriber_id=?",
            (subscriber_id,),
        ).fetchone()
        subscriber = db.execute(
            "SELECT status FROM subscribers WHERE id=?", (subscriber_id,)
        ).fetchone()
        assert request_row is not None
        assert request_row["status"] == "pending"
        assert request_row["stripe_subscription_id"] == "sub_test_123"
        assert subscriber["status"] == "active"
