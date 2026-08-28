# Trading Day Lifecycle

At the beginning of a valid trading day:

1. Prior state must be reconciled.
2. Persisted state and broker state must reconcile.
3. Confirmed eligible funding is reviewed.
4. Prior `next_day_capital` is used.
5. Eligible externally confirmed capital is applied once.
6. An immutable `daily_starting_capital` snapshot is created.
7. The session may begin.

After the last-entry cutoff, new positions are rejected. In the force-exit window, existing positions should be closed. If positions remain after the force-exit deadline, portfolio state becomes `UNCERTAIN` and the system fails closed.

Consecutive closed-trade loss count does not reset merely because a new daily snapshot is created.
