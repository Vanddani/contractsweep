# ContractSweep MVP

A deployable, faceless B2B subscription MVP for commercial-cleaning contract intelligence.

**Working brand only:** `ContractSweep` has not received domain, trademark, or legal clearance. Rename it before public launch if clearance is unavailable.

## What is included

- Conversion-focused public landing page
- Read-only public demo with clearly labeled synthetic opportunities
- One-time passwordless subscriber sign-in
- Searchable opportunity dashboard
- Filters for state, score, deadline, set-aside, and pipeline stage
- Transparent, deterministic 0–100 relevance scoring
- Watch → Qualify → Bid → Won/Lost workflow with notes
- CSV exports
- Commercial-cleaning bid-floor calculator
- Lead capture and admin console
- Manual subscriber activation for concierge validation
- Optional Stripe Payment Link webhook activation
- Optional Resend magic links and weekday digests
- SAM.gov Contract Opportunities v2 ingestion
- SQLite persistence, Dockerfile, Gunicorn, Render blueprint, tests, and launch documents

## The commercial offer

Founding access is configured at **$79/month** by default. The price is intentionally below the eventual target so the first objective is paid validation, not optimization.

Do not add major features until at least five unrelated companies pay and several remain active through three billing cycles.

## Data model and product boundary

The initial feed searches these 2022 NAICS categories:

- `561720` — Janitorial Services
- `561210` — Facilities Support Services
- `561790` — Other Services to Buildings and Dwellings
- `561740` — Carpet and Upholstery Cleaning Services

The product uses the official SAM.gov Contract Opportunities v2 endpoint and requires the operator's public API key. The official API requires `postedFrom`, `postedTo`, and an API key; it supports up to 1,000 records per page. The default 120-day reconciliation window is a practical MVP setting and can be increased up to the API client's 365-day limit after measuring volume. Review the current source documentation before launch:

- https://open.gsa.gov/api/get-opportunities-public-api/
- https://www.census.gov/naics/?details=561720&input=561720&year=2022

The score ranks **category relevance and review priority**. It is not a win probability, bid recommendation, legal opinion, or eligibility determination.

## Local setup

```bash
cd contractsweep_mvp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
flask init-db
flask seed-demo
flask run
```

Open `http://localhost:5000`.

The public demo is enabled by default. Demo accounts are restricted to synthetic `DEMO` records, cannot open or export live subscriber records, and cannot persist pipeline or profile changes. Live subscribers are likewise prevented from seeing synthetic demo records in dashboards, detail pages, exports, or email digests. The local database is created at `data/contractsweep.db` unless `DATABASE_PATH` is changed.

## Required production configuration

Generate long random values rather than reusing the examples:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set at minimum:

```dotenv
SECRET_KEY=...
ADMIN_TOKEN=...
TASK_TOKEN=...
BASE_URL=https://your-domain.example
DATABASE_PATH=/var/data/contractsweep.db
DEMO_MODE=false
ENABLE_PUBLIC_DEMO=true
```

Set `SESSION_COOKIE_SECURE=true` after HTTPS is active.

## Connect live SAM.gov data

1. Create or sign in to a SAM.gov account.
2. Generate a public API key from Account Details.
3. Add it to `.env`:

```dotenv
SAM_API_KEY=your-key
SAM_LOOKBACK_DAYS=120
SAM_NAICS_CODES=561720,561210,561790,561740
DELETE_DEMO_ON_SYNC=true
```

4. Run:

```bash
flask sync-sam
```

For local or single-process operation, schedule `flask sync-sam` once per day. The included Render blueprint instead schedules a cron service that sends an authenticated `POST /tasks/sync` request to the web service. This is intentional: Render cron services cannot access the web service's persistent disk, so the database operation must execute inside the web service.

## Payment setup

The fastest paid-validation workflow is a recurring Stripe Payment Link rather than a custom checkout.

1. Create a monthly recurring product in Stripe.
2. Create a reusable Payment Link for that price.
3. Set:

```dotenv
STRIPE_PAYMENT_LINK=https://buy.stripe.com/...
STRIPE_PAYMENT_LINK_ID=plink_...
```

4. Add a webhook endpoint:

```text
https://your-domain.example/stripe/webhook
```

5. Subscribe it to:

- `checkout.session.completed`
- `customer.subscription.deleted`
- `customer.subscription.paused`
- `customer.subscription.updated`

6. Set the signing secret:

```dotenv
STRIPE_WEBHOOK_SECRET=whsec_...
```

On successful recurring checkout, the MVP activates the purchaser's email and attempts to send a one-time magic sign-in link. Setting `STRIPE_PAYMENT_LINK_ID` limits activation to the intended Payment Link when the Stripe account has other products. Payment Links documentation: https://docs.stripe.com/payment-links

For the first five customers, manual activation from `/admin` is acceptable and often preferable because it preserves direct customer contact.

## Email setup

The app uses Resend's HTTPS API for passwordless sign-in and digests.

```dotenv
RESEND_API_KEY=re_...
EMAIL_FROM=ContractSweep <alerts@your-domain.example>
SUPPORT_EMAIL=support@your-domain.example
```

Verify the sending domain with the provider. Without an email key, `DEMO_MODE=true` shows a local magic link after a login request.

Run a digest manually:

```bash
flask send-digests
```

The included deployment blueprint schedules weekday digests by sending an authenticated `POST /tasks/digests` request to the web service. Adjust the cron expressions in `render.yaml` for the customer timezone and operating cadence you select.

## Scheduled-task security

Set a separate long random `TASK_TOKEN`. Automated jobs must send it in the `X-Task-Token` header or as a Bearer token. The two protected endpoints are:

```text
POST /tasks/sync
POST /tasks/digests
```

Do not reuse `SECRET_KEY`, `ADMIN_TOKEN`, or a payment credential as the task token. The task endpoints are exempt from browser CSRF checks because they use independent token authentication.

## Admin access

Open:

```text
https://your-domain.example/admin
```

Use the configured `ADMIN_TOKEN`. The admin console can:

- Review and export leads
- Activate subscribers manually
- Deactivate access
- Trigger a SAM.gov sync
- Monitor simple inventory counts

The console is appropriate for a concierge MVP, not a large multi-operator company. Add role-based authentication and an audit log before granting access to staff.

## CLI commands

```bash
flask init-db
flask seed-demo
flask sync-sam
flask send-digests
flask create-subscriber --email owner@example.com --company "Example Cleaning" --states "IL,WI"
```

## Run tests

```bash
pytest -q
```

## Deploy with Docker

```bash
docker build -t contractsweep .
docker run --rm -p 5000:5000 --env-file .env -v contractsweep-data:/var/data contractsweep
```

## Deploy on Render

1. Put the project in a private Git repository.
2. Create a new Blueprint from `render.yaml`.
3. Add all `sync: false` environment values.
4. Confirm the persistent disk is mounted at `/var/data`.
5. Set `BASE_URL` to the final HTTPS origin.
6. Trigger the first import from the admin console or send an authenticated `POST /tasks/sync` request. Do not rely on a Render one-off shell job for SQLite disk access.
7. Configure the Stripe webhook only after the final domain is active.

The blueprint uses a paid persistent disk and cron jobs. Review current provider pricing before deployment. Confirm the provider's cron timezone before choosing customer-facing delivery times.

## Paid-validation sequence

1. Connect live data and inspect at least 100 records manually.
2. Adjust keywords and exclusions where false positives are obvious.
3. Record a 90-second screen-only demo.
4. Build a list of 100 janitorial contractors that appear capable of public-sector work.
5. Send 20 personalized messages per business day.
6. Demonstrate the live feed on brief calls or through a screen recording.
7. Charge before custom work.
8. Onboard each customer manually and set states/certifications.
9. Interview each customer after the first digest and again before renewal.
10. Stop or reposition if five unrelated companies will not pay after disciplined outreach.

See `docs/launch_playbook.md` and `docs/outreach_templates.md`.

## Metrics that matter

- Qualified outreach sent
- Positive reply rate
- Paid conversion rate
- Time to first useful match
- Weekly active subscribers
- Digest delivery and click rate
- Opportunities moved to Qualify or Bid
- First-, second-, and third-month retention
- Cancellation reasons
- Weekly operator hours

The first economic gate is not `$5,000 MRR`; it is evidence that a narrow group repeatedly uses and pays for the product.

## Known MVP limitations

- Federal SAM.gov opportunities only; state and local portals are not yet integrated.
- SQLite is suitable for a low-volume MVP, not a large multi-tenant system.
- The feed does not parse solicitation attachments or performance work statements.
- The relevance score is generic, not yet computed against a detailed company capability profile.
- Payment events activate access by checkout email; production billing reconciliation still needs dunning, refunds, and manual exception handling.
- Stripe event IDs are not persisted for a separate webhook-deduplication ledger; handlers are written to be repeatable, but production billing operations still require reconciliation.
- No automated refunds, prorations, seat management, or tax configuration.
- No application-level rate limiter is included; add one before broad public promotion.
- No full terms-of-service/privacy-policy generator is included.
- No guarantee that the working brand or domain is legally available.

## Before scaling

Complete a legal and security review, add database backups, monitoring, rate limiting, stronger admin authentication, data-retention rules, a documented incident process, and explicit terms governing public-source data and user-provided information.
