# 30-Day Paid-Validation Playbook

## Non-negotiable objective

Obtain five unrelated paying commercial-cleaning companies. Do not count friends, free users, compliments, waitlist entries, or promises.

## Days 1–3: Prepare the product

- Replace the working brand only after a domain and basic trademark screen.
- Connect SAM.gov and run the configured 120-day reconciliation import.
- Review the top 100 scored records.
- Record every false positive and adjust `scoring.py` conservatively.
- Configure a real support email, payment link, webhook, and sending domain.
- Test checkout, activation, login, export, pipeline updates, cancellation, and email delivery.
- Publish a concise privacy notice, subscription terms, refund policy, and government-affiliation disclaimer.

**Exit condition:** a stranger can pay, receive access, find an opportunity, and cancel without operator confusion.

## Days 4–7: Build the prospect list

Target owner-led or small-team cleaning companies that:

- Provide recurring commercial janitorial services
- Serve one or more states represented in the feed
- Mention government, education, healthcare, industrial, or institutional clients
- Have enough operational capacity to pursue public work
- Have a business email and identifiable decision-maker

Avoid mass scraping and untargeted blasting. Record the source, decision-maker, service area, evidence of fit, last contact, next action, and outcome in `crm/prospect_tracker.csv`.

**Daily target:** 20 carefully selected prospects.

## Days 8–19: Sell the outcome

Use the sample-opportunity message in `outreach_templates.md`. Personalize one sentence with the prospect's service area or capability.

The call-to-action is not “Would you like software?” It is:

> I can show you the live janitorial opportunities currently matching your service area and how the review queue is ranked. Founding access is $79 per month on a month-to-month basis; the cancellation method and refund policy are disclosed before checkout.

For interested prospects:

1. Show three relevant opportunities.
2. Ask how they currently find bids.
3. Ask what makes an opportunity immediately disqualifying.
4. Ask what a missed viable contract costs them.
5. State the price.
6. Send the payment link during the conversation.

Do not offer custom features before payment. Record requests, but distinguish a recurring pattern from a single preference.

## Days 20–24: Onboard and observe

For each paying customer:

- Confirm service states
- Confirm small-business or socioeconomic certifications
- Set an initial minimum score
- Walk through one live opportunity
- Have the customer move it to Watch, Qualify, or Dismissed
- Ask what information is still missing

Observe whether the product shortens a real task. A customer saying “this looks good” is weaker evidence than a customer using it to decide whether to pursue a notice.

## Days 25–30: Decide

### Continue and improve

Proceed when at least five unrelated customers pay and several use the product without repeated prompting.

Prioritize improvements by frequency and revenue relevance:

1. Company-specific capability scoring
2. Better exclusion of supplies-only notices
3. Attachment/PWS extraction with citations
4. State and local sources for the customers' actual territories
5. Deadline reminders and amendment detection

### Reposition

Reposition when prospects value the feed but reject the segment, source, or workflow. Examples:

- Narrow to healthcare environmental services
- Focus on school-district custodial opportunities in one region
- Sell a weekly human-curated report before maintaining software
- Offer a higher-priced concierge qualification service

### Stop

Stop or change the offer when disciplined, personalized outreach produces no paid conversion and interviews show weak recurring value. Do not respond by adding features to an unvalidated product.

## Weekly scorecard

| Metric | Week 1 | Week 2 | Week 3 | Week 4 |
|---|---:|---:|---:|---:|
| Qualified prospects added |  |  |  |  |
| Personalized messages sent |  |  |  |  |
| Positive replies |  |  |  |  |
| Product demonstrations |  |  |  |  |
| Paid customers |  |  |  |  |
| Active users |  |  |  |  |
| Opportunities moved to Qualify/Bid |  |  |  |  |
| Cancellations |  |  |  |  |
| Operator hours |  |  |  |  |

## Revenue path after validation

A plausible mature mix is not 64 customers at the founding price. Raise pricing after evidence and segment by value:

- Core: 40 customers × $129 = $5,160 MRR
- Team: 10 customers × $249 = $2,490 MRR
- Gross MRR = $7,650

The product must earn the higher price through better matching, broader source coverage, deadline/amendment monitoring, and measurable workflow savings. These figures are targets, not forecasts or guarantees.
