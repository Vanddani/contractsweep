# ContractSweep Policy Pages — Deployment and Review

This update adds public Terms, Privacy, Cancellation/Refund, and Product Disclosure pages; a checkout launch gate; and an authenticated cancellation-request workflow.

## Files included

- `app.py` — current application plus policy routes, legal configuration, cancellation request storage, email confirmations, and admin handling
- `templates/base.html` — footer policy links and subscriber cancellation link
- `templates/index.html` — clear monthly-renewal disclosure and checkout gating
- `templates/admin.html` — pending-cancellation queue and legal launch status
- `templates/terms.html`
- `templates/privacy.html`
- `templates/cancellation_refunds.html`
- `templates/disclosures.html`
- `templates/email_cancellation_confirmation.html`
- `templates/email_cancellation_operator.html`
- `static/styles.css` — policy-page and cancellation-form styles
- `.env.example` and `render.yaml` — legal configuration variables
- `tests/test_app.py` — policy and cancellation tests

## Safe GitHub upload

Extract the update ZIP. Upload the files and folders inside the extracted update folder to the repository root one time. Existing files with the same paths must be replaced; the new templates must remain inside `templates/`.

The repository must still contain exactly one root-level `app.py`.

## Render environment variables

Add these to the main `contractsweep` web service. Do not post the values publicly.

- `LEGAL_SELLER_NAME` — the accurate legal seller description, such as `Full Legal Name, doing business as ContractSweep`. Do not add `LLC` unless an LLC actually exists.
- `LEGAL_MAILING_ADDRESS` — the public mailing address shown in the policies. Separate lines with `|`, such as `Street | City, ST ZIP | United States`.
- `LEGAL_EFFECTIVE_DATE` — the date the reviewed policies become effective.
- `LEGAL_GOVERNING_LAW` — currently `Minnesota`.
- `LEGAL_PAGES_APPROVED` — keep `false` until the text, seller identity, cancellation process, and public address have been reviewed. Set to `true` only when approved for launch.

Keep `STRIPE_PAYMENT_LINK=#request-access` until the policies are reviewed and the production checkout is configured to require acceptance of the Terms.

## URLs to test after deployment

- `/terms`
- `/privacy`
- `/cancellation-refunds`
- `/disclosures`
- `/admin`
- `/health`

## Cancellation acceptance test

1. Sign in as an active non-demo subscriber.
2. Open `/cancellation-refunds`.
3. Submit a cancellation request.
4. Confirm the subscriber receives a request receipt.
5. Confirm the operator receives a support notification.
6. Confirm the request appears in `/admin`.
7. Cancel the matching subscription in live Stripe.
8. Confirm the Stripe webhook deactivates access.
9. Mark the request resolved in `/admin`.

The form records a cancellation request but does not call Stripe directly. The operator must complete the cancellation in Stripe during the MVP stage.

## Review warning

These pages are a practical draft for the current business model, not a substitute for legal advice. A Minnesota attorney should review seller identity, assumed-name status, automatic-renewal disclosures, cancellation timing, refund language, limitation-of-liability language, privacy obligations, and multistate sales before checkout is enabled.
