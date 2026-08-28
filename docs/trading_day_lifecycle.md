# Trading Day Lifecycle

At the beginning of a valid trading day:

1. Prior state must be reconciled.
2. Confirmed eligible funding is reviewed.
3. Prior `next_day_capital` is used.
4. Eligible externally confirmed capital is applied.
5. An immutable `daily_starting_capital` snapshot is created.
6. Daily counters reset.
7. The session may begin.

After the last-entry cutoff, new positions are rejected. In the force-exit window, existing positions should be closed. If positions remain after the force-exit deadline, portfolio state becomes `UNCERTAIN` and the system fails closed.
