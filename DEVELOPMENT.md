# Development roadmap

These are proposed milestones, not claims of completed work. Make future commits when each change is actually implemented and verified.

1. **Issue Desk:** issue editing now preserves audit history and rejects stale versions. Search, priority, and open due-date filters persist in the URL, along with ordering by newest, priority, or due date. Next, add archival and pagination for larger datasets.
2. **Stockroom:** retry-safe receipts and withdrawals are implemented with concurrent-request tests. A streamed full-ledger CSV export includes running balances. Next, add receiving documents and supplier lead-time history.
3. **Experiment Studio:** a direct difference interval and pooled two-proportion test are implemented and checked against published NIST examples. Next, add experiment hypotheses and guardrail metrics. Sample-size planning remains separate from observed outcomes.
4. **Shared backend:** introduce schema migrations, a production HTTP framework, structured logging, and API contract tests.
5. **Multi-user deployment:** add authentication, ownership checks on every record, CSRF protection, and secrets management before exposing the service publicly. Local online snapshots and recovery verification are implemented; encrypted off-device backups and retention remain deployment work.
6. **Frontend quality:** automate browser flows, add screenshot regression checks at desktop and mobile widths, and conduct a keyboard/screen-reader accessibility review.

## Interview walkthrough

- Trace a form submission from JavaScript to validation, SQL, and response handling.
- Explain why checking stock before acquiring the write lock creates a race.
- Explain the tradeoff between a derived ledger balance and a cached stock column.
- Show why repeated status updates do not create duplicate audit entries.
- Explain why a 10% to 12% conversion change is +2 percentage points and +20% relative lift.
- Explain why two per-variant confidence intervals do not establish a winning variant.
- Describe the current security and scaling limitations without claiming production readiness.

## Resume framing

Use claims only after you can explain, maintain, and demonstrate the implementation. Do not describe fictional demo data as business impact or imply real customers.

- Developed a three-app portfolio with JavaScript interfaces, Python JSON APIs, and persistent SQLite storage.
- Implemented a transactional inventory ledger and tested simultaneous withdrawals to prevent negative stock.
- Added audit history, validated experiment analysis, and automated domain/API regression tests with a Python-version CI matrix.

Add measurable performance or user outcomes only after you collect actual evidence. Describe AI assistance honestly if asked about your process.
