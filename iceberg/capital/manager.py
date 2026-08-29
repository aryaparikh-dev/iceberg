from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from iceberg.capital.funding import _FUNDING_LEDGER_TOKEN, FundingLedger
from iceberg.capital.guard import _CAPITAL_MANAGER_TOKEN, CapitalGuard
from iceberg.config.settings import Settings
from iceberg.domain.models import money
from iceberg.exceptions import MarketClosedError, ReconciliationError
from iceberg.market.calendar import TradingCalendar


class CapitalManager:
    """Creates daily immutable capital snapshots from prior capital and confirmed funding."""

    def __init__(
        self,
        capital: CapitalGuard,
        funding_ledger: FundingLedger | None,
        settings: Settings,
        calendar: TradingCalendar,
    ) -> None:
        self.capital = capital
        self.funding_ledger = funding_ledger
        self.settings = settings
        self.calendar = calendar

    def start_trading_day(self, trading_date: date, snapshot_time: datetime) -> Decimal:
        if not self.calendar.is_trading_day(trading_date):
            raise MarketClosedError("cannot create trading snapshot for a closed or unknown market day")
        if self.capital.state.portfolio_state == "UNCERTAIN":
            raise ReconciliationError("cannot start day until portfolio state is reconciled")
        base = money(self.capital.state.next_day_capital)
        eligible = self._eligible_confirmed_events(trading_date, snapshot_time)
        amount = base + sum((event.amount for event in eligible), Decimal("0"))
        created = self.capital._create_daily_snapshot(
            trading_date,
            snapshot_time,
            capital_amount=amount,
            authority_token=_CAPITAL_MANAGER_TOKEN,
        )
        if created and self.funding_ledger is not None:
            for event in eligible:
                self.funding_ledger._mark_applied(event.funding_id, authority_token=_FUNDING_LEDGER_TOKEN)
        return amount

    def apply_intraday_confirmations(self, trading_date: date, now: datetime) -> Decimal:
        if not self.settings.capital.intraday_capital_topups_allowed:
            return self.capital.state.daily_starting_capital
        eligible = self._eligible_confirmed_events(trading_date, now)
        if not eligible:
            return self.capital.state.daily_starting_capital
        amount = sum((event.amount for event in eligible), Decimal("0"))
        self.capital.state.next_day_capital += amount
        if self.funding_ledger is not None:
            for event in eligible:
                self.funding_ledger._mark_applied(event.funding_id, authority_token=_FUNDING_LEDGER_TOKEN)
        return self.capital.state.daily_starting_capital

    def _eligible_confirmed_events(self, trading_date: date, snapshot_time: datetime):
        if self.funding_ledger is None:
            return []
        eligible = []
        for event in self.funding_ledger.confirmed_unapplied():
            if event.effective_trading_date is None or event.confirmed_at is None:
                continue
            if event.effective_trading_date > trading_date:
                continue
            if event.confirmed_at <= snapshot_time or self.settings.capital.intraday_capital_topups_allowed:
                eligible.append(event)
        return eligible
