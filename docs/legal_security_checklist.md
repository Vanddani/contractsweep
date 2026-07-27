# Pre-Launch Legal and Security Checklist

This checklist is operational, not legal advice.

## Business and brand

- [ ] Form and register the operating entity where required
- [ ] Open separate banking and accounting records
- [ ] Check the working name, domain, state records, and relevant trademarks
- [ ] Use a company email and accurate legal seller identity
- [ ] Confirm required business licenses and tax registrations

## Customer terms

- [ ] Subscription terms and automatic-renewal disclosure
- [ ] Clear price, billing frequency, cancellation method, and refund policy
- [ ] Terms of service
- [ ] Privacy notice
- [ ] Acceptable-use terms
- [ ] Disclaimer of government affiliation
- [ ] Disclaimer that scores are not award probabilities or professional advice
- [ ] Limitation-of-liability and warranty language reviewed for the jurisdiction
- [ ] Accessibility review

## Data and source rights

- [ ] Verify each source permits the intended access and commercial use
- [ ] Use official APIs or licensed data rather than prohibited scraping
- [ ] Respect rate limits and attribution requirements
- [ ] Store source URLs and update timestamps
- [ ] Define correction and removal procedures
- [ ] Do not expose API keys in browser code, exports, or public repositories

## Email and outreach

- [ ] Accurate sender identity and subject lines
- [ ] Physical mailing address and opt-out mechanism where required
- [ ] Suppression list honored
- [ ] No deceptive personalization or fabricated relationship
- [ ] Applicable U.S. state, federal, and international rules reviewed for target markets

## Security

- [ ] Separate long random `SECRET_KEY`, `ADMIN_TOKEN`, and `TASK_TOKEN`
- [ ] HTTPS, `SESSION_COOKIE_SECURE=true`, and HSTS verified
- [ ] Secrets stored in the host's secret manager
- [ ] Admin protected by stronger authentication before staff access
- [ ] Rate limiting for login and lead forms
- [ ] Automated encrypted backups and tested restoration
- [ ] Dependency scanning and update process
- [ ] Application and email monitoring
- [ ] Access logging with appropriate retention
- [ ] Incident response owner and procedure
- [ ] Least-privilege access to Stripe, email, hosting, and SAM.gov

## Billing

- [ ] Stripe product and recurring price verified
- [ ] Checkout tax and address settings reviewed
- [ ] Webhook signing secret and intended Payment Link ID configured
- [ ] One-time login link, cancellation flow, and subscription-status updates tested
- [ ] Failed-payment and refund process documented
- [ ] Billing/app-access reconciliation scheduled

## Product claims

- [ ] No passive-income guarantee
- [ ] No contract-award guarantee
- [ ] No claim that every opportunity is complete or current
- [ ] No false customer counts, testimonials, savings, or success rates
- [ ] Synthetic records visibly labeled
- [ ] Marketing metrics supported by actual evidence
