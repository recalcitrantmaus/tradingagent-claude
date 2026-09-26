# state/reviews — naming convention

Adopted 2026-09-26 at recalcitrantmaus's request. One pattern for every file:

    YYYY-MM-DD-TYPE[-TOPIC].md

- **Date:** the ET trading date the file was opened. A weekly review uses
  the Friday that ends its week.
- **TYPE:** one of
  - `queue`: findings from a day's sessions. TOPIC is the finding-ID prefix
    (`queue-m` holds M-n, `queue-f` holds F-n). One prefix per day, and IDs
    are never renumbered.
  - `rca`: a root-cause analysis. TOPIC names the subject (`rca-permissions`).
  - `design`: notes for a design decision (`design-effort`).
  - `weekly-review`: the week's agenda, plus the review's decisions once an
    attended, cleared session runs it.

Files renamed on 2026-09-26 (git history keeps the old names):

| old | new |
|---|---|
| 2026-09-21-eod-queue.md | 2026-09-21-queue-m.md |
| 2026-09-22-queue.md | 2026-09-22-queue-m.md |
| 2026-09-22-tuesday-queue.md | 2026-09-22-queue-t.md |
| 2026-09-23-wednesday-queue.md | 2026-09-23-queue-t.md |
| 2026-09-23-wednesday-close-queue.md | 2026-09-23-queue-w.md |
| 2026-09-25-friday-queue.md | 2026-09-25-queue-f.md |
| 2026-09-25-effort-design-notes.md | 2026-09-25-design-effort.md |
| 2026-09-25-permissions-rca.md | 2026-09-25-rca-permissions.md |
| 2026-W39-review-brief.md | 2026-09-25-weekly-review.md |

The routine prompts in `docs/13*` are stored verbatim, so they keep the old
names. Use the table above to translate them.
