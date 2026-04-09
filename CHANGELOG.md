# Changelog

## 0.3.2
- update the default Polymarket fee formula to `size * rate * price * (1 - price)`
- reduce failed trade logging and display output to trade ids only

## 0.3.1
- log a warning once per market when fee calculation is enabled but `feeSchedule` has not been registered
- document more clearly that callers must provide market fee metadata for fee-aware positions

## 0.3.0
- switch fee calculation to use per-market `feeSchedule` instead of `feeRateBps`
- expose `set_market_fee_schedule` and `set_market_fee_schedules` on `PositionWatcherService`
- apply taker buy fees in shares and taker sell fees in USDC
- add fee-focused trade calculator tests for taker and maker scenarios

## 0.2.9
- add `fee_amount` to `PositionResult` and `UserPosition`
- add `original_size` (pre-fee net size) to `PositionResult` and `UserPosition`
- keep `size` as post-fee net size when `enable_fee_calc=True`

## 0.2.8
- minor cleanup for failed trade size reporting

## 0.2.7
- track failed trades separately and expose failed size in user positions
- skip failed trades when calculating positions and log failed trade details
- allow equal last_update trades to refresh stored entries
- reduce HTTP poll interval default to 1.5s

## 0.2.6
- fix trade message missing, using last_update for update


## 0.2.5

- Add rich table output with `show_positions`/`show_orders` and size/volume totals.
- Preserve and enrich `market_slug` for orders (Gamma API lookup in HTTP loops).
- Add `market_slug` to order model.

## 0.2.3

- Add configurable fee calculation (enable flag + custom function hook).
- Document fee behavior and formula in README (EN/ZH).
- Update example to show fee calculation usage.

## 0.2.4

- Add `trader_side` to TradeMessage schema.
- Apply fee adjustments only when `trader_side` is `TAKER`.
