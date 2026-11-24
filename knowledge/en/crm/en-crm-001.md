# Digital Agency CRM Pipeline and Lead Fields

The following is a configurable starting model, not a universal standard.

## Suggested stages
New → Contacting → Connected → Discovery Scheduled → Discovery Completed → Qualified → Proposal in Progress → Proposal Sent → Negotiation → Won / Lost. Use Nurture for a valid opportunity whose timing is later, and Disqualified when the request is outside the agency's fit or capability.

## Transition rules
- Qualified requires a documented problem, plausible fit, and a next step.
- Proposal Sent requires a proposal version, amount, sent date, and follow-up date.
- Lost requires a reason; no response is not the same as an explicit rejection.
- Nurture requires a review date.
- Every open opportunity has an owner and next action.

## Suggested lead fields
lead_id, created_at, name, company, contact details when voluntarily provided, contact preference/consent, source, campaign, business type, need summary, desired outcome, budget range and confidence, decision role, timeline, owner, status, last contact, next action and due date, loss reason, and notes.

## Data quality
Use controlled values for status and source. Preserve unknowns as null or "unknown"; do not infer missing personal or commercial details. Keep activity history and changes traceable.

## Source basis
Independently authored design informed by Salesforce Help material on lead management, lead fields, assignment, and process stages.
