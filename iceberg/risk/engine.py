from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from iceberg.capital.guard import CapitalGuard
from iceberg.config.settings import Settings, default_settings
from iceberg.domain.enums import Permission, TradeSide, TradingMode
from iceberg.domain.models import MarketDataSnapshot, RiskDecision, TradeProposal, money, require_aware
from iceberg.exceptions import FailClosedError
from iceberg.market.clock import MarketClock
from iceberg.portfolio.portfolio import Portfolio
from iceberg.risk.costs import TransactionCostModel
from iceberg.risk.emergency import EmergencyStop
from iceberg.risk.permissions import PermissionManager


class RiskEngine:
    """Approves or rejects proposals before anything can reach a broker."""

    def __init__(self, settings: Settings | None = None, cost_model: TransactionCostModel | None = None) -> None:
        self.settings = settings or default_settings()
        if cost_model is None:
            from iceberg.risk.costs import FixedTransactionCostModel

            cost_model = FixedTransactionCostModel()
        self.cost_model = cost_model

    def reject(self, reason: str, proposal: TradeProposal, *, risk_assessment: str = "") -> RiskDecision:
        return RiskDecision(
            approved=False,
            decision_id=proposal.decision_id,
            symbol=proposal.symbol,
            side=proposal.side,
            rejection_reason=reason,
            risk_assessment=risk_assessment or reason,
        )

    def approve(
        self,
        proposal: TradeProposal,
        *,
        quantity: int,
        estimated_costs: Decimal,
        gross_trade_value: Decimal,
        capital_required: Decimal,
        risk_assessment: str,
    ) -> RiskDecision:
        return RiskDecision(
            approved=True,
            decision_id=proposal.decision_id,
            symbol=proposal.symbol,
            side=proposal.side,
            quantity=quantity,
            estimated_costs=money(estimated_costs),
            gross_trade_value=money(gross_trade_value),
            capital_required=money(capital_required),
            risk_assessment=risk_assessment,
        )

    def evaluate(
        self,
        proposal: TradeProposal,
        *,
        portfolio: Portfolio,
        capital: CapitalGuard,
        market_data: MarketDataSnapshot | None,
        permissions: PermissionManager,
        emergency_stop: EmergencyStop,
        market_clock: MarketClock,
        now: datetime,
    ) -> RiskDecision:
        require_aware(now, "now")
        if proposal.side is TradeSide.HOLD:
            return self.approve(
                proposal,
                quantity=0,
                estimated_costs=money("0"),
                gross_trade_value=money("0"),
                capital_required=money("0"),
                risk_assessment="HOLD_NO_EXECUTION",
            )
        if not self.settings.testing.paper_trading_enabled:
            return self.reject("PAPER_TRADING_DISABLED", proposal)
        if self.settings.testing.trading_mode is not TradingMode.FULLY_AUTOMATED_PAPER:
            return self.reject("LIVE_TRADING_DISABLED", proposal)
        if self.settings.testing.live_trading_enabled:
            return self.reject("LIVE_TRADING_DISABLED", proposal)
        if not permissions.has(Permission.PAPER_TRADE):
            return self.reject("PERMISSION_DENIED", proposal)
        if emergency_stop.blocks(proposal.side):
            return self.reject("EMERGENCY_STOP", proposal)
        if capital.state.portfolio_state == "UNCERTAIN":
            return self.reject("PORTFOLIO_STATE_UNCERTAIN", proposal)
        if not market_clock.is_market_open(now):
            return self.reject("MARKET_CLOSED", proposal)
        if market_data is None:
            return self.reject("MARKET_DATA_UNAVAILABLE", proposal)
        market_rejection = self._validate_market_data(proposal, market_data, now)
        if market_rejection:
            return self.reject(market_rejection, proposal)

        if proposal.side is TradeSide.BUY:
            return self._evaluate_buy(proposal, portfolio, capital, market_data, market_clock, now)
        if proposal.side is TradeSide.SELL:
            return self._evaluate_sell(proposal, portfolio, capital, market_data)
        return self.reject("UNKNOWN_SIDE", proposal)

    def _evaluate_buy(
        self,
        proposal: TradeProposal,
        portfolio: Portfolio,
        capital: CapitalGuard,
        market_data: MarketDataSnapshot,
        market_clock: MarketClock,
        now: datetime,
    ) -> RiskDecision:
        if not market_clock.can_open_new_position(now):
            return self.reject("LAST_ENTRY_CUTOFF", proposal)
        daily_loss_fraction = self._daily_loss_fraction(capital)
        if daily_loss_fraction >= self.settings.risk.daily_loss_limit_fraction:
            return self.reject("DAILY_LOSS_LIMIT", proposal)
        if capital.state.consecutive_losses >= self.settings.risk.max_consecutive_losses:
            return self.reject("CONSECUTIVE_LOSS_LIMIT", proposal)
        if proposal.symbol not in portfolio.positions and len(portfolio.positions) >= self.settings.risk.maximum_positions:
            return self.reject("MAX_POSITIONS", proposal)

        price = money(proposal.proposed_price)
        current_exposure = portfolio.exposure(proposal.symbol, mark_price=price)
        max_quantity = capital.max_whole_shares_for_price(price, current_exposure)
        if max_quantity <= 0:
            return self.reject("POSITION_LIMIT", proposal)
        quantity = proposal.quantity if proposal.quantity is not None else max_quantity
        if quantity <= 0:
            return self.reject("INVALID_QUANTITY", proposal)
        if quantity > max_quantity:
            return self.reject("POSITION_LIMIT", proposal)
        gross = price * quantity
        if capital.state.deployed_capital + gross > capital.state.daily_starting_capital * self.settings.capital.maximum_portfolio_allocation:
            return self.reject("PORTFOLIO_ALLOCATION_LIMIT", proposal)
        try:
            costs = self.cost_model.estimate(TradeSide.BUY, price, quantity).total
        except Exception:
            return self.reject("TRANSACTION_COSTS_UNAVAILABLE", proposal)
        try:
            spendable = capital.spendable_cash()
        except FailClosedError:
            return self.reject("BROKER_STATE_UNKNOWN", proposal)
        required = gross + costs
        if required > spendable:
            return self.reject("INSUFFICIENT_CASH", proposal)
        if not self.settings.capital.leverage_allowed and capital.state.available_cash - required < 0:
            return self.reject("NO_LEVERAGE", proposal)
        return self.approve(
            proposal,
            quantity=quantity,
            estimated_costs=costs,
            gross_trade_value=gross,
            capital_required=required,
            risk_assessment="APPROVED_BY_RISK_ENGINE",
        )

    def _evaluate_sell(
        self,
        proposal: TradeProposal,
        portfolio: Portfolio,
        capital: CapitalGuard,
        market_data: MarketDataSnapshot,
    ) -> RiskDecision:
        position = portfolio.positions.get(proposal.symbol)
        if position is None:
            return self.reject("NO_POSITION", proposal)
        quantity = proposal.quantity if proposal.quantity is not None else position.quantity
        if quantity <= 0 or quantity > position.quantity:
            return self.reject("INVALID_QUANTITY", proposal)
        price = money(proposal.proposed_price)
        gross = price * quantity
        try:
            costs = self.cost_model.estimate(TradeSide.SELL, price, quantity).total
        except Exception:
            return self.reject("TRANSACTION_COSTS_UNAVAILABLE", proposal)
        return self.approve(
            proposal,
            quantity=quantity,
            estimated_costs=costs,
            gross_trade_value=gross,
            capital_required=money("0"),
            risk_assessment="APPROVED_CONTROLLED_EXIT",
        )

    def _validate_market_data(self, proposal: TradeProposal, market_data: MarketDataSnapshot, now: datetime) -> str | None:
        if market_data.symbol != proposal.symbol:
            return "SYMBOL_MISMATCH"
        if market_data.last_price <= 0 or proposal.proposed_price <= 0:
            return "INVALID_PRICE"
        if market_data.timestamp > now:
            return "FUTURE_MARKET_DATA"
        if market_data.is_stale(now, self.settings.data.max_market_data_age):
            return "STALE_MARKET_DATA"
        if market_data.average_volume is None or market_data.average_volume < self.settings.risk.min_average_volume:
            return "LIQUIDITY_REJECTED"
        if market_data.average_traded_value is None or market_data.average_traded_value < self.settings.risk.min_average_traded_value:
            return "LIQUIDITY_REJECTED"
        if market_data.bid_ask_spread_fraction is None:
            return "LIQUIDITY_REJECTED"
        if market_data.bid_ask_spread_fraction > self.settings.risk.max_bid_ask_spread_fraction:
            return "LIQUIDITY_REJECTED"
        if market_data.recent_activity is not True:
            return "LIQUIDITY_REJECTED"
        if market_data.estimated_price_impact_fraction is None:
            return "LIQUIDITY_REJECTED"
        if market_data.estimated_price_impact_fraction > self.settings.risk.max_estimated_price_impact_fraction:
            return "LIQUIDITY_REJECTED"
        if market_data.abnormal_volatility:
            return "LIQUIDITY_REJECTED"
        return None

    def _daily_loss_fraction(self, capital: CapitalGuard) -> Decimal:
        loss = capital.state.daily_starting_capital - capital.state.total_equity
        if loss <= 0 or capital.state.daily_starting_capital == 0:
            return money("0")
        return loss / capital.state.daily_starting_capital
