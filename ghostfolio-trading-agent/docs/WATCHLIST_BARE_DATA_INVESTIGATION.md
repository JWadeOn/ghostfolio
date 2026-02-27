# Watchlist Bare Data – Investigation

## What you’re seeing

After adding a symbol (e.g. PYPL) to the watchlist, `GET /api/v1/watchlist` returns an item with minimal data:

- `name`: `null`
- `performances.allTimeHigh.performancePercent`: `0`
- `performances.allTimeHigh.date`: missing
- `trend50d` / `trend200d`: `"UNKNOWN"`

## What the API is supposed to return

The watchlist response is built in `apps/api/src/app/endpoints/watchlist/watchlist.service.ts` (`getWatchlistItems`). For each symbol it returns:

| Field | Source | Meaning |
|-------|--------|--------|
| `dataSource`, `symbol` | User’s watchlist (DB) | Identifier |
| `name` | `SymbolProfile` (DB) from `symbolProfileService.getSymbolProfiles()` | Company/asset name |
| `marketCondition` | Derived from all‑time high vs current quote | `ALL_TIME_HIGH` / `BEAR_MARKET` / `NEUTRAL_MARKET` |
| `performances.allTimeHigh.performancePercent` | `(currentPrice - allTimeHigh) / allTimeHigh` | % below all‑time high |
| `performances.allTimeHigh.date` | `marketDataService.getMax()` | Date of all‑time high |
| `trend50d` / `trend200d` | `benchmarkService.getBenchmarkTrends()` from **historical market data** | `UP` / `DOWN` / `NEUTRAL` or `UNKNOWN` |

So “full” data depends on:

1. **Symbol profile** in DB (so `name` is set).
2. **Market data** in DB: at least current quote and historical prices (for all‑time high and 50d/200d trends).
3. **Correct data source** for the asset (e.g. equity data source for stocks like PYPL).

## Root causes

### 1. Wrong data source (e.g. COINGECKO for PYPL)

Your example shows `"dataSource": "COINGECKO"` for **PYPL** (PayPal). PayPal is an equity; CoinGecko is a crypto provider. If the symbol is added with COINGECKO:

- **Name**: The profile may be created from a provider that doesn’t have proper equity metadata, or CoinGecko may not have PYPL at all → `name` stays `null`.
- **Quotes / history**: Equity data may not exist for COINGECKO+PYPL, so no all‑time high, no trends.

The agent resolves `data_source` via Ghostfolio’s symbol lookup (`GET /api/v1/symbol/lookup?query=PYPL`). Lookup runs **all** data sources and merges results (sorted by name). The first exact symbol match can come from any provider (e.g. CoinGecko if it has a PYPL token or similar). The agent was taking that first match and could end up with COINGECKO for a stock.

**Fix (agent):** When resolving data source for watchlist (and similar flows), prefer **equity** data sources (e.g. YAHOO, FINANCIAL_MODELING_PREP) over **crypto** (e.g. COINGECKO) when the symbol looks like a stock ticker. Prefer matches with `assetSubClass !== 'CRYPTOCURRENCY'` when the API returns it.

### 2. Data gathering is asynchronous

In `createWatchlistItem`, the backend:

1. Ensures a `SymbolProfile` exists (create from provider if needed).
2. Calls `dataGatheringService.gatherSymbol({ dataSource, symbol })`.
3. Connects the symbol to the user’s watchlist.

`gatherSymbol` **enqueues** jobs (Bull queue); it does **not** wait for historical data to be written. So right after add:

- **MarketData** table may still be empty for that symbol.
- `marketDataService.getMax()` → `null` → no all‑time high, so `performancePercent` is 0 and `date` is missing.
- `benchmarkService.getBenchmarkTrends()` uses `marketDataService.marketDataItems()` (last 400 days). With no data, `calculateBenchmarkTrend` returns `'UNKNOWN'` because it requires at least `2 * days` points (e.g. 100 for 50d, 400 for 200d).

So even with the **correct** data source, the first time you open the watchlist after adding a symbol, data can still look “bare” until the gathering job has run and backfilled history.

**Fix (product/UX):** Either:

- Document that watchlist enrichment (name, performance, trends) may appear after a short delay (e.g. 1–2 minutes), or
- Have the backend optionally wait for or trigger higher‑priority sync gathering for the new watchlist symbol (more involved).

### 3. Sort can throw when `name` is null

In `getWatchlistItems`, the list is sorted by:

```ts
return watchlist.sort((a, b) => a.name.localeCompare(b.name));
```

If any item has `name === null`, this can throw. With a single item it might not crash, but with multiple items and one null name it can.

**Fix (API):** Sort safely, e.g. `(a.name ?? '').localeCompare(b.name ?? '')` so null names are handled and ordered consistently.

## Summary

| Issue | Cause | Fix |
|-------|--------|-----|
| `name: null` | Wrong data source (e.g. COINGECKO for PYPL) or profile not enriched yet | Prefer equity data source in agent; ensure profile comes from a provider that has the name. |
| `performancePercent: 0`, no `date` | No market data in DB yet (gathering queued, not run) | Wait for gathering to run; or trigger/await sync gather for new watchlist items. |
| `trend50d` / `trend200d`: `UNKNOWN` | No historical market data (need 100+ / 400+ days) | Same as above; trends appear after backfill. |
| Possible API crash on sort | `a.name` or `b.name` null | Use null‑safe sort in watchlist service. |

Implementing the agent-side data-source preference and the watchlist sort fix addresses the wrong-data-source case and avoids sort crashes; the “bare” data right after add will still occur until the data-gathering job has run, unless the backend is extended to wait for or prioritize that gather.
