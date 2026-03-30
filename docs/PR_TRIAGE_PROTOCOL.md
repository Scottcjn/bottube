# PR Triage Protocol — Elyan Labs

## The Problem
During high-volume triage, real contributions from legitimate accounts get
batch-closed alongside spam. This loses contributors and unpaid work.

## The Rule
**No PR may be closed without a review comment unless ALL of these are true:**
1. Account is < 7 days old AND
2. PR has 0 changed files OR body is empty AND
3. PR does not address a labeled bounty issue

If ANY of those conditions is false → the PR MUST get a human-readable
close comment explaining why, with an invitation to resubmit.

## Triage Tiers

### Tier 1: Auto-Close (no review needed)
- 0 files changed
- Body is empty or only a wallet address
- Account created same day as PR
- Known spam pattern (duplicate of already-merged PR, exact copy)

### Tier 2: Quick Review (30-second check)
- Account < 30 days old
- Changed files < 3
- Additions < 50 lines
- Close with: "Thank you for the submission. [specific reason]. Here's how to improve: [guidance]."

### Tier 3: Real Review Required (cannot skip)
Triggers when ANY of these are true:
- **Account age > 6 months**
- **Additions > 200 lines of non-generated code**
- **PR addresses a labeled bounty issue**
- **PR includes tests**
- **PR touches security-related code**
- **Contributor has previously merged PRs**

These PRs MUST be:
1. Read (at minimum, skim the diff)
2. Given specific feedback if closing
3. Offered resubmission guidance if the code is good but format is wrong

### Tier 4: Priority Review
- Known trusted contributors (createkr, B1tor, CelebrityPunks, danielalanbates, etc.)
- Security findings
- PRs from accounts with 50+ repos or 100+ followers

## The Diff Padding Problem
Many contributors submit good code wrapped in bad diffs (rewriting unrelated files).

**Response protocol:**
1. Identify which files are the REAL contribution
2. Comment: "Your [feature] code looks solid. However, this PR also modifies [X] unrelated files. Please resubmit with only the [feature] files in a fresh branch from main."
3. Reserve the RTC amount
4. Do NOT silently close

## Payment Protocol
- Merged PR = payment owed within 72 hours
- If wallet format is wrong, respond within 24 hours asking for correct format
- Track all pending payments in the BOUNTY_LEDGER
- Never let a payment go > 7 days without followup

## Batch Triage Sessions
When doing 20+ PRs at once:
1. Sort by account age (oldest first)
2. Process Tier 3/4 individually
3. Batch Tier 1 closes
4. Tier 2 gets template responses customized per PR
5. At the end, review the close list — any with >100 additions get a second look

## Tools
- Claude Code agents: Use for initial categorization
- Codex: Cross-reference to confirm close decisions
- Neither should auto-close Tier 3+ PRs without human approval
