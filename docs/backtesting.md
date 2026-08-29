# Backtesting

Backtest results are not guaranteed live results. Research outputs can be distorted by survivorship bias, look-ahead bias, corporate-action errors, bad data, liquidity assumptions, slippage assumptions, and transaction-cost uncertainty.

`BacktestEngine` uses the same `CapitalGuard`, `RiskEngine`, `TransactionCostModel`, and `PaperBroker` path as paper trading.

It accounts for:

- whole shares
- 10% per-stock cap
- cash availability
- transaction costs
- market hours
- liquidity checks
- stale-data rejection
- rejected-trade reporting
- no future candle access at decision time
- explicit transaction-cost model
- explicit slippage model
- explicit liquidity assumptions when true liquidity inputs are unavailable
- participation-rate limits using observed historical volume when supplied
- multi-symbol mark-to-market using latest valid prices for every open position
- daily forced exits and settlement
- user distributions
- next-bar-open execution after bar-close signals
- trade-ledger and daily-equity-curve outputs
- benchmark comparison architecture
- train/validation/test and walk-forward research utilities

Strategies receive only the candle history available at the current timestamp. The default convention is `SIGNAL_ON_BAR_CLOSE_EXECUTE_NEXT_BAR_OPEN`, so a strategy cannot decide using a candle close and receive a fill at that same close unless a future explicit simulation convention is added and documented.

If liquidity/spread/impact inputs are absent, the backtester does not silently fabricate safe values. A caller must either accept rejection or pass an explicit `SimulatedLiquidityAssumptionProfile`, and the report flags that assumptions were used.

Forced exits require an actual candle or tick inside the configured force-exit window. The backtester does not relabel an older intraday price as a 15:20 exit; if no valid exit-window price exists for an open position, the day fails closed, marks portfolio state uncertain, and does not settle.

The default execution convention remains:

```text
SIGNAL_ON_BAR_CLOSE -> EXECUTE_NEXT_BAR_OPEN
```

A strategy cannot observe a candle close and receive a fill at that same close. At identical timestamps, multi-symbol processing is deterministic by `(timestamp, symbol)`, and each strategy receives only that symbol's timestamp-available history.

Backtest reports include gross profit, transaction costs, slippage, net profit, rejected-trade counts, unavailable-metric reasons, adjustment mode, survivorship-bias status, trade ledger entries, daily equity curve points, regime analysis, and attribution by symbol, month, year, strategy, and regime.

The research CLI is available through:

```text
python -m iceberg.research validate-data --csv PATH --symbol SYMBOL
python -m iceberg.research normalize-data --csv PATH --symbol SYMBOL --output-name NAME
python -m iceberg.research backtest --csv PATH --symbol SYMBOL --strategy momentum --assume-liquidity
python -m iceberg.research compare --csv PATH --symbol SYMBOL --strategies momentum,breakout --assume-liquidity
python -m iceberg.research walk-forward --start 2019-01-01 --end 2024-12-31 --train-days 730 --validation-days 180 --test-days 180 --step-days 180
```

The CLI has no live broker, bank, withdrawal, or transfer command.
