# MVP Architecture

```text
SAM.gov v2 API
      ^
      |
Render cron --POST + task token--> web service /tasks/sync
                                      |
                                      v
                          SQLite on persistent disk
                                      |
                         deterministic relevance score
                                      |
                                      +--> subscriber dashboard
                                      |      |       |
                                      |      |       +--> CSV export
                                      |      +----------> pipeline notes/stages
                                      +-----------------> filtered email digest

Stripe Payment Link --> signed webhook --> subscriber activation --> one-time magic link
Landing form -----------------------------------------------> admin lead queue
Render cron --POST + task token--> web service /tasks/digests
```

## Why the scheduled jobs call the web service

Render cron jobs cannot access another service's persistent disk. The cron containers therefore make authenticated HTTP requests to the web service. The web service performs the SQLite work on its own mounted disk. `TASK_TOKEN` is separate from the browser CSRF token, admin token, Flask secret, and payment credentials.

## Why this architecture

- Fast to deploy and inexpensive enough for paid validation
- No custom frontend build pipeline
- One stateful web service, two short cron callers, and no separate queue
- SQLite is adequate for a low-concurrency MVP and easy to export
- Cross-worker task locks prevent overlapping imports and digest runs
- One-time passwordless links avoid retaining subscriber passwords
- Manual admin controls preserve close contact with founding customers
- External services are limited to data, payments, email, and hosting

## Trust boundaries

- Only the server receives the SAM.gov key, Stripe webhook secret, Resend key, admin token, and task token.
- Browser forms use session-bound CSRF tokens.
- Stripe webhooks are checked against the raw request body and signing secret.
- Public demo users are restricted to synthetic `DEMO` records and cannot persist pipeline or profile changes.
- Live subscribers are restricted to non-demo records across dashboards, detail pages, exports, pipeline actions, and digests.
- The relevance score is deterministic and does not claim to predict an award.

## Upgrade triggers

Move from SQLite to PostgreSQL when concurrency, analytics, data volume, or deployment topology require it. Add a task queue when ingestion and document parsing exceed safe HTTP task duration. Add object storage before accepting customer uploads or storing solicitation attachments. Add tenant-aware roles, audit logging, and stronger admin identity before team accounts or staff access.
