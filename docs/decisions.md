# Decision Log

A running record of decisions that diverge from the original plan, newest at the top. One line each: what changed, and why. Claude Code appends here automatically when we lock in a decision that differs from what the docs described. See CLAUDE.md for the routing rules on which doc each kind of decision updates.

Format: `YYYY-MM-DD  what changed  (why)`

## Decisions

- 2026-07-10  Data comes from Finnhub and we run our own simulation, instead of using Alpaca's paper-trading engine for execution (Alpaca paper accounts are one-per-login and do not fan out to a multi-user app cleanly; our own cash/holdings/transactions model is simpler and multi-user native).