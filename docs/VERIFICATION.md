# Production verification

A written pass over the deployed service with its real providers, done after the first deploy and
again after code freeze. It is written failures first: the reader should learn what is broken before
what works. Copy the template below for each audit, newest at the top, and keep the old ones.

The scripted part already runs on every deploy (`scripts/deploy.sh` ends with the live smoke: every
GET below 500, a request without the token refused). This document covers what a script cannot:
the journeys a judge or user will take, real email and calls, the agent's actual behaviour.

## Safety rules

Read these before the first request. They apply to every person and agent doing the audit.

1. **Owned inboxes and numbers only.** Email goes only to inboxes the team controls, calls only to
   numbers the team owns. List them in the audit's Reference line. Nobody else is contacted, even
   by accident: if the product could reach a stranger, that path is tested in simulate mode or not
   at all.
2. **Synthetic records only.** Every record the audit creates is made up and carries the audit's
   reference ID in its name or body, so it can be found and removed. No real person's data.
3. **No infrastructure changes.** No deploy, DNS, scheduler, secret, IAM or billing change during
   the audit. `gcloud` is used read-only (`describe`, `list`, `logging read`).
4. **Agents get a production-test clause.** Any product agent run during the audit is told: "This
   is a production test. Take no real-world action except to the listed test recipients, and
   contact nobody else." Effects stay `EFFECTS=simulate` unless a row needs a live send to an
   owned recipient.
5. **Anything not tried is "not tested".** Never a pass, never left out. A failure of the test
   harness is not a product defect, and it is not a pass either: it is "not tested".
6. **Stop on real harm.** A message to someone not on the list, a charge, a deleted real record:
   stop, record it as the first finding, and tell the deploy owner.
7. **Evidence stays.** Logs, request IDs and screenshots go somewhere durable and private that is
   named in the audit (a bucket path), never `/tmp`.

---

## Template

### YYYY-MM-DD production audit, `<reference-id>`

**Result:** `<N>` failures, `<M>` not tested. This is not an all-pass result. *(Write "all
checked rows passed" only when the Failures and Not tested tables are both empty.)*

**Reference:** service `<url>`, release `commit=<sha> revision=<name>` (the `release:` line from
`deploy.sh`), auditor `<name or agent>`, test recipients `<owned inboxes and numbers>`, evidence
in `<private bucket path>`.

#### Failures

| # | Finding | Evidence | Consequence | Fix |
|---|---|---|---|---|
| 1 | What went wrong, in one sentence | The request, response code, log line or screenshot that shows it | Who it hurts and how badly | Commit and regression test, or "open"; "retested: pass" once the row is re-run |

#### Not tested

| What | Why not |
|---|---|
| A journey or check that was not tried | Unsafe under the rules, provider not configured, harness broke, ran out of time |

#### Verified

| Command or journey | Result |
|---|---|
| Live smoke: `BASE_URL=<url> ADMIN_PASSWORD=... uv run pytest -q -m live` | `<n> passed` |
| A journey, step by step, as a judge would take it | What was seen, with the evidence path |

#### Cleanup

What was removed (synthetic records by reference ID, temporary grants, sessions), and what was
deliberately left in production for traceability.
