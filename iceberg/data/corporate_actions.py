from __future__ import annotations

from dataclasses import replace

from iceberg.data.models import AdjustmentMode, CorporateAction, CorporateActionStatus, CorporateActionType, HistoricalBar
from iceberg.domain.models import money
from iceberg.exceptions import FailClosedError


class CorporateActionAdjuster:
    def adjust(
        self,
        bars: list[HistoricalBar] | tuple[HistoricalBar, ...],
        actions: list[CorporateAction] | tuple[CorporateAction, ...],
        mode: AdjustmentMode,
    ) -> tuple[HistoricalBar, ...]:
        mode = AdjustmentMode(mode)
        if mode is AdjustmentMode.RAW:
            return tuple(replace(bar, adjustment_mode=mode) for bar in bars)
        if not actions:
            raise FailClosedError(f"{mode.value} requires corporate-action data")
        adjusted = tuple(bars)
        for action in sorted(actions, key=lambda item: item.ex_date):
            if action.action_type in {CorporateActionType.SPLIT, CorporateActionType.BONUS}:
                adjusted = self._apply_split_like(adjusted, action, mode)
            elif action.action_type is CorporateActionType.DIVIDEND and mode is AdjustmentMode.TOTAL_RETURN_ADJUSTED:
                adjusted = self._apply_dividend(adjusted, action, mode)
            elif action.action_type in {CorporateActionType.SYMBOL_CHANGE, CorporateActionType.MERGER, CorporateActionType.DELISTING}:
                adjusted = tuple(
                    replace(bar, corporate_action_status=CorporateActionStatus.AVAILABLE)
                    if bar.symbol == action.symbol
                    else bar
                    for bar in adjusted
                )
        return adjusted

    def _apply_split_like(
        self,
        bars: tuple[HistoricalBar, ...],
        action: CorporateAction,
        mode: AdjustmentMode,
    ) -> tuple[HistoricalBar, ...]:
        if action.ratio is None or action.ratio <= 0:
            raise FailClosedError("split/bonus adjustment requires a positive ratio")
        ratio = action.ratio
        result = []
        for bar in bars:
            if bar.symbol == action.symbol and bar.trading_date < action.ex_date:
                result.append(
                    replace(
                        bar,
                        open=bar.open / ratio,
                        high=bar.high / ratio,
                        low=bar.low / ratio,
                        close=bar.close / ratio,
                        volume=bar.volume * ratio,
                        adjustment_mode=mode,
                        corporate_action_status=CorporateActionStatus.APPLIED,
                    )
                )
            else:
                result.append(replace(bar, adjustment_mode=mode, corporate_action_status=CorporateActionStatus.APPLIED))
        return tuple(result)

    def _apply_dividend(
        self,
        bars: tuple[HistoricalBar, ...],
        action: CorporateAction,
        mode: AdjustmentMode,
    ) -> tuple[HistoricalBar, ...]:
        if action.cash_amount is None or action.cash_amount < 0:
            raise FailClosedError("dividend adjustment requires a non-negative cash amount")
        result = []
        for bar in bars:
            if bar.symbol == action.symbol and bar.trading_date < action.ex_date:
                adjustment = min(action.cash_amount, bar.low - money("0.01"))
                result.append(
                    replace(
                        bar,
                        open=bar.open - adjustment,
                        high=bar.high - adjustment,
                        low=bar.low - adjustment,
                        close=bar.close - adjustment,
                        adjustment_mode=mode,
                        corporate_action_status=CorporateActionStatus.APPLIED,
                    )
                )
            else:
                result.append(replace(bar, adjustment_mode=mode, corporate_action_status=CorporateActionStatus.APPLIED))
        return tuple(result)
