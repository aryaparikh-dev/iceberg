from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from iceberg.capital.guard import CapitalGuard
from iceberg.domain.models import TradeProposal
from iceberg.market.clock import MarketClock
from iceberg.portfolio.portfolio import Portfolio


class ExitManager:
    def __init__(self, market_clock: MarketClock) -> None:
        self.market_clock = market_clock

    def create_force_exit_proposals(
        self,
        portfolio: Portfolio,
        prices: dict[str, Decimal],
        now: datetime,
    ) -> list[TradeProposal]:
        if not self.market_clock.is_force_exit_window(now):
            return []
        proposals: list[TradeProposal] = []
        for symbol, position in portfolio.positions.items():
            if symbol not in prices:
                continue
            proposals.append(
                TradeProposal.sell(
                    symbol,
                    price=prices[symbol],
                    quantity=position.quantity,
                    decision_id=f"force-exit-{symbol}-{now.isoformat()}",
                    timestamp=now,
                    strategy="ExitManager",
                    summary="Forced intraday exit",
                )
            )
        return proposals

    def mark_uncertain_after_deadline(self, portfolio: Portfolio, capital: CapitalGuard, now: datetime) -> None:
        if self.market_clock.force_exit_deadline_passed(now) and not portfolio.is_flat():
            capital.mark_portfolio_uncertain()
