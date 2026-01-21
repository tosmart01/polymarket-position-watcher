# Changelog

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
