# Changelog
## 0.3.9
- sync the default fee behavior with the current Polymarket fees docs: taker buy and taker sell both keep shares unchanged and charge fees in USDC
- update fee-related tests, example output labels, and README fee semantics

## 0.3.8
- fix fee_rate_bps typing error

## 0.3.7
- add `wait_for_orders_pos_filled(...)` for waiting on position synchronization via `position.original_size`
- enhance `wait_for_orders_filled(...)` results with aggregate fields and direct `get(order_id)` / `is_filled(order_id)` helpers
- document the order-scoped wait APIs and `get_effective_position_size(...)` usage in the example and README

## 0.3.6
- add `group` namespaces to HTTP fallback listen APIs while keeping old calls compatible via the default group
- add `set_http_listen(...)` for atomic per-group HTTP monitor replacement

## 0.3.5
- add `get_position_by_order_ids(...)` and `get_positions_by_order_ids(...)` for strategy-level position queries
- index only the current user's related order ids from live trades, ignoring unrelated maker orders in API payloads
- allow order snapshots without `original_size` to be stored safely

## 0.3.4
- normalize trade event timestamps across `match_time`, `last_update`, and `timestamp`
- prevent empty trade timestamps from breaking position calculation, HTTP sorting, and trade dedupe

## 0.3.3
- warn about failed trades only once per `token_id + trade.id` pair to avoid repeated websocket log spam

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
