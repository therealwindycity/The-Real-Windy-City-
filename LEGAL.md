# Legal & Ethics Contract

This engine goes after public records hard, but only by legal means. The rules
below are enforced in code, not only described here. If a configuration would
break one of them, the configuration is wrong.

## Hard rules

1. **Public records only.** No logins, paywall circumvention, session spoofing,
   CAPTCHA solving or endpoint probing.
2. **`robots.txt` is honored**, including `Crawl-delay`, for our real User-Agent
   (`engine/net.py`). A `401/403/451` response or an unreadable-because-forbidden
   robots file counts as a refusal.
3. **No disguise.** The User-Agent identifies the project and a contact address.
   There is no user-agent spoofing and no "stealth" browser mode. The optional
   Playwright tier renders JS-heavy pages *only after* robots allows them.
4. **A refusal becomes a records request, never a workaround.** Blocked sources
   generate a `blocked_source` event and a drafted bulk-access request under the
   state's public-records law. That route gets the same public records while
   avoiding terms-of-service or computer-access-law exposure (for example under
   the CFAA).
5. **Rate discipline.** At least 3 seconds between hits per host by default,
   bounded documents per source per run, and headlines plus summaries only for
   news feeds (no full-article scraping).
6. **A human sends every records request.** Requests are drafts. The engine
   computes deadlines and flags overdue responses, but it never contacts an
   agency itself. Alerts go to you, never to officials.
7. **Public-official scope.** No personal addresses, personal phone numbers,
   family members or other non-public personal data in watchlists or output.
   Crime data is used only in aggregate.
8. **Accuracy over narrative.** Every event carries a verbatim quote, a source
   URL and a fetch timestamp. Output from the optional LLM pass is kept only when
   each quote it returns is confirmed to appear verbatim in the source, and it is
   labeled with the model name.
9. **Tamper-evident record.** The public ledger is hash-chained, and git history
   serves as a second witness.

## Not legal advice

Statute citations and deadlines in `config/statutes.json` are starting points.
Laws change, so verify them before relying on them. For high-stakes denials, contact
a local media-law attorney, your state press association, or the Reporters
Committee for Freedom of the Press legal hotline.
