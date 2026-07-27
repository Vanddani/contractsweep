# Operator Runbook

## Daily

1. Confirm `/health` returns `status: ok`.
2. Confirm the SAM sync job completed.
3. Review new high-scoring records for obvious supplies-only or unrelated results.
4. Review failed emails and subscriber replies.
5. Respond to active founding customers within one business day.
6. Send personalized outreach to the day's qualified prospects.

## Weekly

1. Export leads and reconcile each with the prospect tracker.
2. Review every record moved to Qualify, Bid, Won, or Lost.
3. Interview at least one active customer.
4. Review cancellations and non-conversion objections.
5. Record false positives and missing categories.
6. Back up the database.
7. Review Stripe subscriptions against active app access.
8. Record operator hours.

## Manual database backup

Stop writes briefly or use SQLite's backup command:

```bash
sqlite3 /var/data/contractsweep.db ".backup '/var/data/contractsweep-backup-$(date +%F).db'"
```

Store encrypted copies outside the hosting account. Define and test a restore procedure before accepting significant revenue.

## Add a subscriber manually

```bash
flask create-subscriber \
  --email owner@example.com \
  --company "Example Cleaning" \
  --states "IL,WI"
```

Or use `/admin`.

## Re-run data ingestion

For local Docker or a host process with direct access to the database:

```bash
flask sync-sam
```

On Render, use the admin console or call the protected web task endpoint because one-off and cron processes cannot access the web service's disk:

```bash
curl -X POST \
  -H "X-Task-Token: $TASK_TOKEN" \
  "$BASE_URL/tasks/sync"
```

A valid `SAM_API_KEY` must be configured. If the command fails:

- Check the API key
- Check required date formatting and lookback range
- Check provider status and rate limits
- Inspect the HTTP error recorded in the command output
- Do not repeatedly retry a rate-limited key

## Email failure

- Confirm the sending domain is verified
- Confirm `RESEND_API_KEY` and `EMAIL_FROM`
- Confirm the recipient is syntactically valid
- Review provider logs
- For an active paying customer, generate a new sign-in link through the admin activation flow only after confirming identity through the subscribed email address

## Stripe reconciliation

At least weekly, compare:

- Active Stripe subscriptions
- Active non-demo rows in `subscribers`
- Canceled or unpaid accounts
- Checkout emails that differ from user-requested emails

The webhook is an MVP convenience, not a substitute for billing reconciliation. Confirm that the configured `STRIPE_PAYMENT_LINK_ID` matches the recurring offer and review `customer.subscription.updated` handling when billing policies change.

## Data-quality policy

- Never represent synthetic demo entries as real.
- Confirm that demo accounts remain read-only and that paying accounts never receive `DEMO` records after application changes.
- Never claim that a score predicts award likelihood.
- Never remove official-source links.
- Do not copy restricted or licensed data into the feed without permission.
- Use official APIs, public pages, or properly licensed sources.
- Record the source and update time for every future integration.

## Incident response minimum

1. Disable affected access or integrations.
2. Preserve logs and a database copy.
3. Determine which users and data were affected.
4. Rotate keys and tokens.
5. Follow applicable contractual and legal notification duties.
6. Document cause, correction, and prevention.

Obtain professional security and legal guidance before the product stores sensitive business documents or serves a substantial customer base.
