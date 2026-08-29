from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from iceberg.capital.guard import CapitalState
from iceberg.domain.enums import FundingStatus, TradeSide
from iceberg.domain.models import OrderExecution, Position, money
from iceberg.persistence.database import SQLiteDatabase


def _decimal(value: str | None) -> Decimal | None:
    return None if value is None else money(value)


def _dt(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def _date(value: str | None) -> date | None:
    return None if value is None else date.fromisoformat(value)


class SQLiteStateStore:
    def __init__(self, path: str | Path) -> None:
        self.db = SQLiteDatabase(path)

    def transaction(self):
        return self.db.transaction()

    def _commit(self) -> None:
        if self.db.transaction_depth == 0:
            self.db.connection.commit()

    def account_state_exists(self) -> bool:
        checks = (
            "SELECT 1 FROM capital_state WHERE id = 1 LIMIT 1",
            "SELECT 1 FROM daily_snapshots LIMIT 1",
            "SELECT 1 FROM funding_events LIMIT 1",
            "SELECT 1 FROM portfolio_positions LIMIT 1",
            "SELECT 1 FROM executions LIMIT 1",
            "SELECT 1 FROM decision_ids LIMIT 1",
            "SELECT 1 FROM idempotency_keys LIMIT 1",
            "SELECT 1 FROM emergency_stop WHERE id = 1 LIMIT 1",
        )
        return any(self.db.connection.execute(query).fetchone() is not None for query in checks)

    def save_capital_state(self, state: CapitalState) -> None:
        self.db.connection.execute(
            """
            INSERT OR REPLACE INTO capital_state (
                id, starting_capital, daily_starting_capital, available_cash,
                broker_available_cash, settled_cash, unsettled_cash, deployed_capital,
                realized_pnl, unrealized_pnl, market_value, total_equity,
                user_distribution, next_day_capital, current_trading_date,
                snapshot_created_at, consecutive_losses, broker_state_known,
                portfolio_state
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(state.starting_capital),
                str(state.daily_starting_capital),
                str(state.available_cash),
                None if state.broker_available_cash is None else str(state.broker_available_cash),
                str(state.settled_cash),
                str(state.unsettled_cash),
                str(state.deployed_capital),
                str(state.realized_pnl),
                str(state.unrealized_pnl),
                str(state.market_value),
                str(state.total_equity),
                str(state.user_distribution),
                str(state.next_day_capital),
                state.current_trading_date.isoformat() if state.current_trading_date else None,
                state.snapshot_created_at.isoformat() if state.snapshot_created_at else None,
                state.consecutive_losses,
                int(state.broker_state_known),
                state.portfolio_state,
            ),
        )
        self._commit()

    def load_capital_state(self) -> CapitalState | None:
        row = self.db.connection.execute("SELECT * FROM capital_state WHERE id = 1").fetchone()
        if row is None:
            return None
        return CapitalState(
            starting_capital=money(row["starting_capital"]),
            daily_starting_capital=money(row["daily_starting_capital"]),
            available_cash=money(row["available_cash"]),
            broker_available_cash=_decimal(row["broker_available_cash"]),
            settled_cash=money(row["settled_cash"]),
            unsettled_cash=money(row["unsettled_cash"]),
            deployed_capital=money(row["deployed_capital"]),
            realized_pnl=money(row["realized_pnl"]),
            unrealized_pnl=money(row["unrealized_pnl"]),
            market_value=money(row["market_value"]),
            total_equity=money(row["total_equity"]),
            user_distribution=money(row["user_distribution"]),
            next_day_capital=money(row["next_day_capital"]),
            current_trading_date=_date(row["current_trading_date"]),
            snapshot_created_at=_dt(row["snapshot_created_at"]),
            consecutive_losses=row["consecutive_losses"],
            broker_state_known=bool(row["broker_state_known"]),
            portfolio_state=row["portfolio_state"],
        )

    def save_daily_snapshot(self, trading_date: date, snapshot_created_at: datetime, amount: Decimal) -> bool:
        cur = self.db.connection.execute(
            """
            INSERT OR IGNORE INTO daily_snapshots
            (trading_date, snapshot_created_at, daily_starting_capital)
            VALUES (?, ?, ?)
            """,
            (trading_date.isoformat(), snapshot_created_at.isoformat(), str(amount)),
        )
        self._commit()
        return cur.rowcount == 1

    def locked_snapshot_dates(self) -> set[date]:
        rows = self.db.connection.execute("SELECT trading_date FROM daily_snapshots").fetchall()
        return {date.fromisoformat(row["trading_date"]) for row in rows}

    def save_funding_event(self, event) -> None:
        self.db.connection.execute(
            """
            INSERT OR REPLACE INTO funding_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.funding_id,
                str(event.amount),
                event.currency,
                event.requested_at.isoformat(),
                event.confirmed_at.isoformat() if event.confirmed_at else None,
                event.effective_trading_date.isoformat() if event.effective_trading_date else None,
                event.external_reference,
                event.status.value,
                event.created_by,
                event.notes,
            ),
        )
        self._commit()

    def load_funding_events(self):
        from iceberg.capital.funding import FundingEvent

        rows = self.db.connection.execute("SELECT * FROM funding_events").fetchall()
        return [
            FundingEvent(
                funding_id=row["funding_id"],
                amount=money(row["amount"]),
                currency=row["currency"],
                requested_at=datetime.fromisoformat(row["requested_at"]),
                confirmed_at=_dt(row["confirmed_at"]),
                effective_trading_date=_date(row["effective_trading_date"]),
                external_reference=row["external_reference"],
                status=FundingStatus(row["status"]),
                created_by=row["created_by"],
                notes=row["notes"],
            )
            for row in rows
        ]

    def save_positions(self, positions: dict[str, Position]) -> None:
        self.db.connection.execute("DELETE FROM portfolio_positions")
        for position in positions.values():
            self.db.connection.execute(
                "INSERT INTO portfolio_positions VALUES (?, ?, ?, ?)",
                (position.symbol, position.quantity, str(position.average_price), str(position.cost_basis)),
            )
        self._commit()

    def load_positions(self) -> dict[str, Position]:
        rows = self.db.connection.execute("SELECT * FROM portfolio_positions").fetchall()
        return {
            row["symbol"]: Position(
                symbol=row["symbol"],
                quantity=row["quantity"],
                average_price=money(row["average_price"]),
                cost_basis=money(row["cost_basis"]),
            )
            for row in rows
        }

    def save_execution(self, execution: OrderExecution) -> None:
        self.db.connection.execute(
            """
            INSERT OR REPLACE INTO executions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                execution.order_id,
                execution.decision_id,
                execution.idempotency_key,
                execution.symbol,
                execution.side.value,
                execution.quantity,
                str(execution.execution_price),
                str(execution.gross_value),
                str(execution.transaction_costs),
                str(execution.net_cash_flow),
                execution.timestamp.isoformat() if execution.timestamp else None,
                execution.status,
                execution.rejection_reason,
                str(execution.slippage),
                str(execution.gross_pnl),
                str(execution.net_pnl),
                execution.charge_schedule_version,
            ),
        )
        self.db.connection.execute(
            "INSERT OR REPLACE INTO idempotency_keys VALUES (?, ?)",
            (execution.idempotency_key, execution.order_id),
        )
        if execution.status != "REJECTED":
            self.db.connection.execute(
                "INSERT OR REPLACE INTO decision_ids VALUES (?, ?)",
                (execution.decision_id, execution.order_id),
            )
        self._commit()

    def load_executions(self) -> list[OrderExecution]:
        rows = self.db.connection.execute("SELECT * FROM executions").fetchall()
        return [
            OrderExecution(
                order_id=row["order_id"],
                decision_id=row["decision_id"],
                idempotency_key=row["idempotency_key"],
                symbol=row["symbol"],
                side=TradeSide(row["side"]),
                quantity=row["quantity"],
                execution_price=money(row["execution_price"]),
                gross_value=money(row["gross_value"]),
                transaction_costs=money(row["transaction_costs"]),
                net_cash_flow=money(row["net_cash_flow"]),
                timestamp=_dt(row["timestamp"]),
                status=row["status"],
                rejection_reason=row["rejection_reason"],
                slippage=money(row["slippage"]),
                gross_pnl=money(row["gross_pnl"]),
                net_pnl=money(row["net_pnl"]),
                charge_schedule_version=row["charge_schedule_version"],
            )
            for row in rows
        ]

    def load_decision_ids(self) -> set[str]:
        rows = self.db.connection.execute("SELECT decision_id FROM decision_ids").fetchall()
        return {row["decision_id"] for row in rows}

    def load_executions_by_idempotency(self) -> dict[str, OrderExecution]:
        return {execution.idempotency_key: execution for execution in self.load_executions()}

    def save_emergency_stop(self, *, active: bool, allow_position_exits: bool) -> None:
        self.db.connection.execute(
            "INSERT OR REPLACE INTO emergency_stop VALUES (1, ?, ?)",
            (int(active), int(allow_position_exits)),
        )
        self._commit()

    def load_emergency_stop(self) -> tuple[bool, bool] | None:
        row = self.db.connection.execute("SELECT * FROM emergency_stop WHERE id = 1").fetchone()
        if row is None:
            return None
        return bool(row["active"]), bool(row["allow_position_exits"])

    def save_audit_record(self, record) -> None:
        self.db.connection.execute(
            """
            INSERT INTO audit_records (
                timestamp, decision_id, symbol, side, strategy, market_regime, confidence,
                key_signals, features, quantity, proposed_price, approved_quantity,
                estimated_costs, capital_required, risk_result, rejection_reason,
                authorization_id, order_id, execution_price, slippage, gross_pnl,
                transaction_costs, net_pnl, charge_schedule_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.timestamp.isoformat() if record.timestamp else None,
                record.decision_id,
                record.symbol,
                record.decision,
                record.strategy,
                record.market_regime,
                None if record.confidence is None else str(record.confidence),
                json.dumps(record.key_signals),
                json.dumps(record.relevant_features, default=str),
                record.quantity,
                str(record.proposed_price),
                record.quantity,
                str(record.estimated_costs),
                str(record.capital_required),
                record.risk_decision,
                record.rejection_reason,
                record.authorization_id,
                record.order_id,
                None if record.execution_price is None else str(record.execution_price),
                str(record.slippage),
                str(record.gross_pnl),
                str(record.transaction_costs),
                str(record.net_pnl),
                record.charge_schedule_version,
            ),
        )
        self._commit()

    def save_reconciliation_status(self, *, portfolio_state: str, broker_state_known: bool, reason: str | None, updated_at: datetime | None) -> None:
        self.db.connection.execute(
            "INSERT OR REPLACE INTO reconciliation_status VALUES (1, ?, ?, ?, ?)",
            (portfolio_state, int(broker_state_known), reason, updated_at.isoformat() if updated_at else None),
        )
        self._commit()

    def close(self) -> None:
        self.db.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
