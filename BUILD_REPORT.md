# ContractSweep MVP — Build and Launch Report

**Build date:** July 26, 2026  
**Status:** Deployable MVP package; external services are not connected  
**Working brand:** ContractSweep — domain, trademark, and legal clearance have not been completed

## 1. Product delivered

ContractSweep is a faceless, online B2B subscription product for commercial-cleaning contract intelligence. It converts public federal procurement records into a filtered review queue, transparent relevance scores, deadline-aware alerts, and a lightweight bid pipeline.

The initial commercial offer is configured at **$79 per month** for founding customers. The product is intentionally scoped for paid validation before custom development or broader data coverage.

### Public acquisition layer

- Conversion-focused landing page
- Founding offer and recurring-payment call to action
- Lead-capture form
- Read-only public demo using visibly synthetic records
- Bid-floor calculator
- Responsive desktop and mobile layouts
- Brand-owned, face-free presentation

### Subscriber product

- One-time, 30-minute passwordless sign-in links
- Searchable opportunity dashboard
- State, score, deadline, set-aside, active-status, and pipeline filters
- Deterministic 0–100 relevance score with visible reasons
- Opportunity detail pages with official-source links and contacts
- Watch → Qualify → Bid → Won/Lost/Dismissed pipeline
- Private notes
- CSV export with spreadsheet-formula neutralization
- Configurable state, set-aside, and minimum-score alert profile
- Weekday email digest of newly first-seen matches

### Operator layer

- Lead queue and CSV export
- Manual subscriber activation/deactivation
- SAM.gov synchronization control
- Inventory metrics excluding synthetic demo records
- CLI commands for database setup, demo seeding, synchronization, digests, and subscriber creation
- Prospect-tracking CSV and launch/outreach playbooks

### Integrations and deployment

- SAM.gov Contract Opportunities v2 API ingestion
- Stripe recurring Payment Link webhook activation
- Stripe subscription status updates
- Resend transactional email and digests
- SQLite persistence with WAL mode, foreign keys, 30-second busy timeout, and task locks
- Docker and Gunicorn runtime
- Render Blueprint with persistent disk
- Token-protected HTTP scheduled tasks for synchronization and digests

## 2. Data scope

The first release searches the following 2022 NAICS categories:

| NAICS | Category |
|---|---|
| 561720 | Janitorial Services |
| 561210 | Facilities Support Services |
| 561790 | Other Services to Buildings and Dwellings |
| 561740 | Carpet and Upholstery Cleaning Services |

The default synchronization window is 120 days. Records are deduplicated by SAM.gov notice ID, normalized, rescored, and reconciled against the current window. The score estimates category relevance and review priority; it is not a win probability, eligibility determination, legal opinion, or bid recommendation.

## 3. Security and data-isolation controls implemented

- Production startup fails when `SECRET_KEY` or `ADMIN_TOKEN` is absent.
- Browser POST requests require a session-bound CSRF token.
- Stripe webhooks verify the raw request body and signing secret.
- Scheduled task endpoints require an independent constant-time-compared task token.
- Magic links are single-use and expire after 30 minutes.
- Session cookies are HTTP-only and SameSite=Lax; Secure and HSTS are enabled through production configuration.
- Content Security Policy, frame denial, MIME sniffing protection, referrer restrictions, and private/no-store caching are set.
- External links are restricted to absolute HTTP or HTTPS URLs.
- Redirect targets are restricted to same-origin relative paths.
- CSV exports neutralize values that spreadsheet programs could interpret as formulas.
- Public demo accounts can only read synthetic `DEMO` records and cannot persist pipeline or profile changes.
- Live subscribers cannot see synthetic demo records in dashboards, detail pages, exports, pipeline actions, or digests.
- Demo records are removed after a successful live synchronization by default.
- Overlapping synchronization and digest tasks are blocked with database task locks.
- The Docker image runs as a non-root user.

## 4. Validation completed

| Validation | Result |
|---|---|
| Python bytecode compilation | Passed |
| Python AST parsing | Passed for 9 source/test files |
| Framework-independent unit tests | **9/9 passed** |
| SQLite schema execution | Passed |
| Required tables and indexes | Passed |
| Independent demo/live SQL isolation simulation | Passed |
| Jinja template compilation | Passed for 11 templates |
| Route inventory | Passed; 22 routes detected |
| Browser POST form CSRF audit | Passed |
| Static asset reference audit | Passed |
| Render Blueprint structure and task architecture | Passed |
| Live-looking credential scan | Passed |
| Security hardening assertions | Passed |
| Desktop visual review | Passed at 1440 px width |
| Mobile visual review | Passed at 390 px width |

### Validation not executable in this build environment

The Flask integration suite in `tests/test_app.py` was compiled but not executed because this sandbox does not contain Flask, Werkzeug, or the Stripe Python package, and dependency downloads are blocked. The distributable pins those dependencies in `requirements.txt`; run the complete suite after installation:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

A live SAM.gov request, signed Stripe webhook, real email delivery, and production Render deployment were not executed because no user-owned API keys, payment account, sending domain, deployment account, or final domain was supplied.

## 5. Credentials and decisions required before launch

### Mandatory

1. **Final domain and HTTPS origin** for `BASE_URL`.
2. **SAM.gov public API key** for `SAM_API_KEY`.
3. **Stripe monthly recurring Payment Link** and its `plink_...` ID.
4. **Stripe webhook signing secret** for the final `/stripe/webhook` endpoint.
5. **Resend API key** and a verified sending domain.
6. **Real sender and support addresses** for `EMAIL_FROM` and `SUPPORT_EMAIL`.
7. **Brand/domain/trademark clearance** or a replacement working name.
8. **Subscription terms, privacy notice, cancellation/refund terms, and government-affiliation disclaimer** reviewed for the operating jurisdiction.

### Generated by the Render Blueprint

- `SECRET_KEY`
- `ADMIN_TOKEN`
- `TASK_TOKEN`

Store the generated values securely. Do not reuse them across roles.

## 6. Deployment sequence

1. Rename the working brand if clearance is unavailable.
2. Put this directory in a private Git repository.
3. Create the Render Blueprint from `render.yaml`.
4. Enter every environment variable marked `sync: false`.
5. Confirm the persistent disk is mounted at `/var/data`.
6. Set `BASE_URL` to the final HTTPS origin.
7. Deploy and confirm `/health` returns an OK response.
8. Run the first SAM.gov synchronization from the admin console or protected task endpoint.
9. Manually inspect at least 100 records and adjust scoring phrases if false positives are material.
10. Create the Stripe recurring Payment Link and configure the final signed webhook.
11. Verify the email sending domain and test a one-time sign-in link.
12. Create one real test subscriber and run the complete acceptance checklist.
13. Replace placeholder seller/support information and publish reviewed legal terms.
14. Begin concierge sales to the first 100 qualified prospects.

## 7. Paid-validation gate

Do not expand the product merely because the software works. Continue only when the market evidence supports it.

The initial gate is:

- Five unrelated companies pay.
- Customers receive at least one useful match quickly.
- Several customers remain through three billing cycles.
- Customers use the dashboard, digest, or pipeline rather than merely praising the idea.
- Weekly operator work can be documented and delegated.

At the configured founding price, 64 customers equal $5,056 in gross monthly recurring revenue. This is not net income; payment processing, hosting, email, contractor quality control, refunds, taxes, and acquisition costs must be deducted.

## 8. Known MVP limitations

- Federal SAM.gov records only; state, local, university, and private portals are not integrated.
- Solicitation attachments and performance work statements are not parsed.
- SQLite is suitable for low-volume validation, not a high-concurrency platform.
- No application-level rate limiter is included.
- Admin authentication uses a single token and is not appropriate for multiple staff users.
- Stripe event IDs are not stored in a separate webhook-deduplication ledger.
- Billing requires manual reconciliation for failed payments, refunds, email mismatches, taxes, and exceptions.
- No automated database backup service or external monitoring is configured.
- No customer uploads, document storage, team seats, roles, audit log, or in-app billing portal.
- The relevance score is generic rather than trained or calibrated against each contractor's capabilities.
- The working name and marketing statements have not been legally cleared.

## 9. Included operating documents

- `README.md` — setup, configuration, and deployment
- `docs/launch_playbook.md` — first-customer validation process
- `docs/outreach_templates.md` — faceless email and follow-up copy
- `docs/operator_runbook.md` — daily and weekly operations
- `docs/legal_security_checklist.md` — pre-launch controls
- `docs/architecture.md` — system design and upgrade triggers
- `crm/prospect_tracker.csv` — initial sales pipeline schema

## 10. Acceptance test after dependencies and credentials are installed

Run the following before accepting a real payment:

```bash
pytest -q
flask init-db
flask sync-sam
flask create-subscriber --email your-test-address@example.com --company "Acceptance Test" --states "IL"
flask send-digests
```

Then verify manually:

- HTTPS and HSTS
- Public demo is read-only
- Demo users cannot see live data
- Live users cannot see demo data
- Magic link works once and expires
- Dashboard filters, detail pages, pipeline, profile, and CSV export
- Stripe test checkout activates only the intended recurring Payment Link
- Cancellation or pause deactivates access
- Digest uses the subscriber's filters and contains only newly first-seen live records
- Database backup and restore
- Terms, privacy notice, refund/cancellation process, support address, and seller identity

---

This package is a functioning validation-stage product, not evidence that the market will purchase it. Revenue depends on data quality, sales execution, retention, costs, and compliant operation.
