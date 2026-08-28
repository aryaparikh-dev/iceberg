# Backtesting

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
- multi-symbol mark-to-market using latest valid prices for every open position
- daily forced exits and settlement
- user distributions
- next-bar-open execution after bar-close signals

Strategies receive only the candle history available at the current timestamp. The default convention is `SIGNAL_ON_BAR_CLOSE_EXECUTE_NEXT_BAR_OPEN`, so a strategy cannot decide using a candle close and receive a fill at that same close unless a future explicit simulation convention is added and documented.

If liquidity/spread/impact inputs are absent, the backtester does not silently fabricate safe values. A caller must either accept rejection or pass an explicit `SimulatedLiquidityAssumptionProfile`, and the report flags that assumptions were used.
