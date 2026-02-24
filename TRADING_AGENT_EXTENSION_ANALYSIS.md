# Ghostfolio Trading Intelligence Agent — Extension Point Analysis

**Purpose:** Identify every extension point for building a LangGraph-based AI agent for short-term traders (1 day–3 month holding periods): opportunity discovery, chart validation, market regime detection, and performance improvement.

---

## 1. API Endpoints Inventory

All REST endpoints live under `apps/api/src/app/`. Controllers use NestJS decorators; routes are prefixed by `@Controller()` and use `AuthGuard('jwt')` or `AuthGuard('api-key')` unless noted. **Classification:** (a) agent calls directly as tool, (b) agent extends, (c) ignore.

### Portfolio (`/portfolio`)

| Method | Route                                         | Query/Body                                                                                                                              | Returns                           | Classification |
| ------ | --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------- | -------------- |
| GET    | `/portfolio/details`                          | `accounts?`, `assetClasses?`, `dataSource?`, `range` (DateRange, default: 'max'), `symbol?`, `tags?`, `withMarkets?` (default: 'false') | `PortfolioDetails & { hasError }` | **(a)**        |
| GET    | `/portfolio/dividends`                        | `accounts?`, `assetClasses?`, `dataSource?`, `groupBy?`, `range`, `symbol?`, `tags?`                                                    | `PortfolioDividendsResponse`      | **(a)**        |
| GET    | `/portfolio/holding/:dataSource/:symbol`      | —                                                                                                                                       | `PortfolioHoldingResponse`        | **(a)**        |
| GET    | `/portfolio/holdings`                         | `accounts?`, `assetClasses?`, `dataSource?`, `holdingType?`, `query?`, `range`, `symbol?`, `tags?`                                      | `PortfolioHoldingsResponse`       | **(a)**        |
| GET    | `/portfolio/investments`                      | `accounts?`, `assetClasses?`, `dataSource?`, `groupBy?`, `range`, `symbol?`, `tags?`                                                    | `PortfolioInvestmentsResponse`    | **(a)**        |
| GET    | `/portfolio/performance`                      | `accounts?`, `assetClasses?`, `dataSource?`, `range`, `symbol?`, `tags?`, `withExcludedAccounts?`                                       | `PortfolioPerformanceResponse`    | **(a)**        |
| GET    | `/portfolio/report`                           | —                                                                                                                                       | `PortfolioReportResponse`         | **(a)**        |
| PUT    | `/portfolio/holding/:dataSource/:symbol/tags` | Body: `UpdateHoldingTagsDto`                                                                                                            | void                              | **(b)**        |

### Order / Activity (`/order`)

| Method | Route        | Query/Body                                                                                                                   | Returns                | Classification |
| ------ | ------------ | ---------------------------------------------------------------------------------------------------------------------------- | ---------------------- | -------------- |
| GET    | `/order`     | `accounts?`, `assetClasses?`, `dataSource?`, `range?`, `skip?`, `sortColumn?`, `sortDirection?`, `symbol?`, `tags?`, `take?` | `ActivitiesResponse`   | **(a)**        |
| GET    | `/order/:id` | —                                                                                                                            | `ActivityResponse`     | **(a)**        |
| POST   | `/order`     | Body: `CreateOrderDto`                                                                                                       | `OrderModel`           | **(a)**        |
| PUT    | `/order/:id` | Body: `UpdateOrderDto`                                                                                                       | `OrderModel`           | **(a)**        |
| DELETE | `/order/:id` | —                                                                                                                            | `OrderModel`           | **(b)**        |
| DELETE | `/order`     | `accounts?`, `assetClasses?`, `dataSource?`, `symbol?`, `tags?`                                                              | number (deleted count) | **(c)**        |

### Market Data (`/market-data`)

| Method | Route                              | Query/Body                        | Returns                       | Classification |
| ------ | ---------------------------------- | --------------------------------- | ----------------------------- | -------------- |
| GET    | `/market-data/markets`             | `includeHistoricalData?` (number) | `MarketDataOfMarketsResponse` | **(a)**        |
| GET    | `/market-data/:dataSource/:symbol` | —                                 | `MarketDataDetailsResponse`   | **(a)**        |
| POST   | `/market-data/:dataSource/:symbol` | Body: `UpdateBulkMarketDataDto`   | `Prisma.BatchPayload`         | **(b)**        |

### Symbol (`/symbol`)

| Method | Route                                     | Query/Body                        | Returns                          | Classification |
| ------ | ----------------------------------------- | --------------------------------- | -------------------------------- | -------------- |
| GET    | `/symbol/lookup`                          | `includeIndices?`, `query?`       | `LookupResponse`                 | **(a)**        |
| GET    | `/symbol/:dataSource/:symbol`             | `includeHistoricalData?` (number) | `SymbolItem`                     | **(a)**        |
| GET    | `/symbol/:dataSource/:symbol/:dateString` | —                                 | `DataProviderHistoricalResponse` | **(a)**        |

### Account (`/account`)

| Method | Route                       | Query/Body                         | Returns                   | Classification |
| ------ | --------------------------- | ---------------------------------- | ------------------------- | -------------- |
| GET    | `/account`                  | `dataSource?`, `query?`, `symbol?` | `AccountsResponse`        | **(a)**        |
| GET    | `/account/:id`              | —                                  | `AccountResponse`         | **(a)**        |
| GET    | `/account/:id/balances`     | —                                  | `AccountBalancesResponse` | **(a)**        |
| POST   | `/account`                  | Body: `CreateAccountDto`           | `AccountModel`            | **(b)**        |
| PUT    | `/account/:id`              | Body: `UpdateAccountDto`           | `AccountModel`            | **(b)**        |
| POST   | `/account/transfer-balance` | Body: `TransferBalanceDto`         | void                      | **(c)**        |
| DELETE | `/account/:id`              | —                                  | `AccountModel`            | **(c)**        |

### Watchlist (`/watchlist`)

| Method | Route                            | Query/Body                     | Returns             | Classification |
| ------ | -------------------------------- | ------------------------------ | ------------------- | -------------- |
| GET    | `/watchlist`                     | —                              | `WatchlistResponse` | **(a)**        |
| POST   | `/watchlist`                     | Body: `CreateWatchlistItemDto` | `WatchlistItem`     | **(a)**        |
| DELETE | `/watchlist/:dataSource/:symbol` | —                              | void                | **(a)**        |

### Benchmarks (`/benchmarks`)

| Method | Route                                              | Query/Body                     | Returns                              | Classification |
| ------ | -------------------------------------------------- | ------------------------------ | ------------------------------------ | -------------- |
| GET    | `/benchmarks`                                      | —                              | `BenchmarkResponse`                  | **(a)**        |
| GET    | `/benchmarks/:dataSource/:symbol/:startDateString` | `range`, `accounts?`, etc.     | `BenchmarkMarketDataDetailsResponse` | **(a)**        |
| POST   | `/benchmarks`                                      | Body: `AssetProfileIdentifier` | `Benchmark`                          | **(c)**        |
| DELETE | `/benchmarks/:dataSource/:symbol`                  | —                              | `Benchmark`                          | **(c)**        |

### AI (`/ai`)

| Method | Route              | Query/Body                                                      | Returns            | Classification |
| ------ | ------------------ | --------------------------------------------------------------- | ------------------ | -------------- |
| GET    | `/ai/prompt/:mode` | `accounts?`, `assetClasses?`, `dataSource?`, `symbol?`, `tags?` | `AiPromptResponse` | **(a)**        |

### Data Provider Ghostfolio (API Key) (`/data-providers/ghostfolio`)

| Method | Route                                              | Query/Body                  | Returns                                      | Classification |
| ------ | -------------------------------------------------- | --------------------------- | -------------------------------------------- | -------------- |
| GET    | `/data-providers/ghostfolio/asset-profile/:symbol` | —                           | `DataProviderGhostfolioAssetProfileResponse` | **(a)**        |
| GET    | `/data-providers/ghostfolio/dividends/:symbol`     | `from`, `to`, `granularity` | `DividendsResponse`                          | **(a)**        |
| GET    | `/data-providers/ghostfolio/historical/:symbol`    | `from`, `to`, `granularity` | `HistoricalResponse`                         | **(a)**        |
| GET    | `/data-providers/ghostfolio/lookup`                | `includeIndices?`, `query?` | `LookupResponse`                             | **(a)**        |
| GET    | `/data-providers/ghostfolio/quotes`                | `symbols`                   | `QuotesResponse`                             | **(a)**        |
| GET    | `/data-providers/ghostfolio/status`                | —                           | `DataProviderGhostfolioStatusResponse`       | **(a)**        |

### Other Agent-Relevant Endpoints

| Controller    | Method | Route                                                                           | Classification                   |
| ------------- | ------ | ------------------------------------------------------------------------------- | -------------------------------- |
| User          | GET    | `/user`                                                                         | **(a)** — user context           |
| Asset         | GET    | `/asset/:dataSource/:symbol`                                                    | **(a)**                          |
| Exchange Rate | GET    | `/exchange-rate/:symbol/:dateString`                                            | **(a)**                          |
| Tags          | GET    | `/tags`                                                                         | **(a)**                          |
| Platform      | GET    | `/platform`, GET `/platforms`                                                   | **(a)**                          |
| Info          | GET    | `/info`                                                                         | **(a)**                          |
| Health        | GET    | `/health`, `/health/data-provider/:dataSource`, `/health/data-enhancer/:name`   | **(a)**                          |
| Public        | GET    | `/public/:accessId/portfolio`                                                   | **(a)** — public portfolio       |
| Admin         | POST   | `/admin/gather`, `/admin/gather/max`, `/admin/gather/:dataSource/:symbol`, etc. | **(b)** — trigger data gathering |
| Import        | POST   | `/import`                                                                       | **(b)**                          |
| Export        | GET    | `/export`                                                                       | **(b)**                          |
| API Keys      | POST   | `/api-keys`                                                                     | **(b)** — for agent auth         |

### Summary

- **Call directly (a):** ~50 endpoints (portfolio, orders, market data, symbols, watchlist, benchmarks, AI prompt, health, user, asset, exchange rate, tags, platforms).
- **Extend (b):** ~20 (gather, import, account/order creation, tags, settings, API keys).
- **Ignore (c):** ~50 (auth flows, admin user/settings, subscriptions, logos, sitemap, cache flush, etc.).

---

## 2. Data Provider Architecture

### Interface Location

**File:** `apps/api/src/services/data-provider/interfaces/data-provider.interface.ts`

### DataProviderInterface Methods

| Method                                                               | Signature (conceptual)                                                              | Purpose                                     |
| -------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ------------------------------------------- |
| `canHandle(symbol: string)`                                          | `boolean`                                                                           | Whether this provider can handle the symbol |
| `getAssetProfile({ symbol, requestTimeout? })`                       | `Promise<Partial<SymbolProfile>>`                                                   | Profile metadata for symbol                 |
| `getDataProviderInfo()`                                              | `DataProviderInfo`                                                                  | Name, URL, isPremium, dataSource            |
| `getDividends({ from, to, symbol, granularity?, requestTimeout? })`  | `Promise<{ [date: string]: DataProviderHistoricalResponse }>`                       | Dividend history                            |
| `getHistorical({ from, to, symbol, granularity?, requestTimeout? })` | `Promise<{ [symbol: string]: { [date: string]: DataProviderHistoricalResponse } }>` | OHLCV-style history                         |
| `getQuotes({ symbols, requestTimeout? })`                            | `Promise<{ [symbol: string]: DataProviderResponse }>`                               | Current/latest quotes                       |
| `search({ query, includeIndices?, requestTimeout?, userId? })`       | `Promise<LookupResponse>`                                                           | Symbol search                               |
| `getName()`                                                          | `DataSource`                                                                        | Enum value for this provider                |
| `getTestSymbol()`                                                    | `string`                                                                            | Symbol used for health checks               |
| `getMaxNumberOfSymbolsPerRequest?()`                                 | `number` (optional)                                                                 | Batch size for quotes                       |

**Param types:** `GetAssetProfileParams`, `GetDividendsParams`, `GetHistoricalParams`, `GetQuotesParams`, `GetSearchParams` (all in same file). **Granularity** comes from `@ghostfolio/common/types` (e.g. day).

### Implementing Classes (9 total)

| Class                        | File                                                   | DataSource              |
| ---------------------------- | ------------------------------------------------------ | ----------------------- |
| YahooFinanceService          | `data-provider/yahoo-finance/yahoo-finance.service.ts` | YAHOO                   |
| RapidApiService              | `data-provider/rapid-api/rapid-api.service.ts`         | RAPID_API               |
| ManualService                | `data-provider/manual/manual.service.ts`               | MANUAL                  |
| GoogleSheetsService          | `data-provider/google-sheets/google-sheets.service.ts` | GOOGLE_SHEETS           |
| GhostfolioService            | `data-provider/ghostfolio/ghostfolio.service.ts`       | GHOSTFOLIO              |
| FinancialModelingPrepService | `data-provider/financial-modeling-prep/`               | FINANCIAL_MODELING_PREP |
| EodHistoricalDataService     | `data-provider/eod-historical-data/`                   | EOD_HISTORICAL_DATA     |
| CoinGeckoService             | `data-provider/coingecko/coingecko.service.ts`         | COINGECKO               |
| AlphaVantageService          | `data-provider/alpha-vantage/alpha-vantage.service.ts` | ALPHA_VANTAGE           |

### Provider Registration

**File:** `apps/api/src/services/data-provider/data-provider.module.ts`

- All 9 services are in the `providers` array.
- A factory provider `'DataProviderInterfaces'` injects all 9 and returns an array.
- `DataProviderService` is injected with `@Inject('DataProviderInterfaces')` and uses `getDataProvider(providerName: DataSource)` to select by name.

**Adding a new provider (e.g. social sentiment or options flow):**

1. Add a new value to the `DataSource` enum in `prisma/schema.prisma` and run migration.
2. Create a new service class implementing `DataProviderInterface` (same method signatures).
3. Register the service in `DataProviderModule` and add it to the factory’s `inject` and returned array.
4. Optionally add env/config (e.g. API key) and include the source in `DATA_SOURCES` or provider-specific config so it can be enabled.

### DataProviderService (orchestration)

**File:** `apps/api/src/services/data-provider/data-provider.service.ts`

- `getQuotes()`: groups by data source, batches by `getMaxNumberOfSymbolsPerRequest()`, uses Redis cache, can update `MarketData`.
- `getHistorical()`: checks DB first, then providers.
- `getHistoricalRaw()`: direct provider fetch (no DB).
- `getAssetProfiles()`, `search()`, `getDataSources()`, `validateActivities()`.

---

## 3. Prisma Schema Analysis

**File:** `prisma/schema.prisma`

### Existing Models (summary)

| Model                      | Key fields                                                                                                                                                           | Relations                                                                                    |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| **User**                   | id, provider, role, accessToken, thirdPartyId                                                                                                                        | accounts, activities, watchlist (SymbolProfile[]), tags, settings, apiKeys, accessesGet/Give |
| **Account**                | id, userId (composite PK), name, balance, currency, platformId, isExcluded                                                                                           | activities (Order[]), balances, platform, user                                               |
| **AccountBalance**         | id, accountId, userId, date, value                                                                                                                                   | account                                                                                      |
| **Order**                  | id, userId, accountId, accountUserId, date, symbolProfileId, type, quantity, unitPrice, fee, currency, isDraft, comment                                              | account, user, SymbolProfile, tags                                                           |
| **SymbolProfile**          | id, dataSource, symbol (unique with dataSource), currency, name, assetClass, assetSubClass, isin, sectors, countries, holdings (Json), scraperConfiguration, userId? | activities, user (creator), watchedBy (User[]), SymbolProfileOverrides                       |
| **SymbolProfileOverrides** | symbolProfileId (PK), name, assetClass, assetSubClass, sectors, countries, holdings, url                                                                             | SymbolProfile                                                                                |
| **MarketData**             | id, dataSource, symbol, date, marketPrice, state (CLOSE/INTRADAY)                                                                                                    | — (unique on dataSource+date+symbol)                                                         |
| **Platform**               | id, name, url (unique)                                                                                                                                               | accounts                                                                                     |
| **Tag**                    | id, name, userId?                                                                                                                                                    | activities (Order[])                                                                         |
| **Access**                 | id, userId, granteeUserId, permissions, settings, alias                                                                                                              | user, granteeUser                                                                            |
| **ApiKey**                 | id, userId, hashedKey                                                                                                                                                | user                                                                                         |
| **Property**               | key (PK), value                                                                                                                                                      | —                                                                                            |
| **Settings**               | userId (PK), settings (Json), updatedAt                                                                                                                              | user                                                                                         |
| **Analytics**              | userId (PK), activityCount, country, dataProviderGhostfolioDailyRequests, lastRequestAt                                                                              | user                                                                                         |
| **AuthDevice**             | id, userId, credentialId, credentialPublicKey, counter                                                                                                               | user                                                                                         |
| **Subscription**           | id, userId, expiresAt, price                                                                                                                                         | user                                                                                         |
| **AssetProfileResolution** | id, dataSourceOrigin/Target, symbolOrigin/Target, currency, requestCount                                                                                             | —                                                                                            |

### Enums

- **DataSource:** ALPHA_VANTAGE, COINGECKO, EOD_HISTORICAL_DATA, FINANCIAL_MODELING_PREP, GHOSTFOLIO, GOOGLE_SHEETS, MANUAL, RAPID_API, YAHOO
- **MarketDataState:** CLOSE, INTRADAY
- **AssetClass:** ALTERNATIVE_INVESTMENT, COMMODITY, EQUITY, FIXED_INCOME, LIQUIDITY, REAL_ESTATE
- **AssetSubClass:** BOND, CASH, COLLECTIBLE, COMMODITY, CRYPTOCURRENCY, ETF, MUTUALFUND, PRECIOUS_METAL, PRIVATE_EQUITY, STOCK
- **Type** (order): BUY, SELL, DIVIDEND, FEE, INTEREST, LIABILITY
- **Role:** ADMIN, DEMO, INACTIVE, USER
- **AccessPermission:** READ, READ_RESTRICTED

### Proposed New Models for the Agent

```prisma
model Signal {
  id          String   @id @default(uuid())
  userId      String
  user        User     @relation(fields: [userId], onDelete: Cascade, references: [id])
  symbol      String
  dataSource  DataSource
  symbolProfileId String?
  symbolProfile   SymbolProfile? @relation(fields: [symbolProfileId], references: [id])
  strategyId String?
  strategy   Strategy? @relation(fields: [strategyId], references: [id])
  direction   String   // LONG | SHORT
  strength   Float?   // 0-1 or score
  rationale  String?  // text from agent
  chartSnapshot Json? // optional chart/TA context
  createdAt   DateTime @default(now())
  expiresAt  DateTime?
  @@index([userId])
  @@index([strategyId])
  @@index([dataSource, symbol])
}

model Strategy {
  id          String   @id @default(uuid())
  userId      String
  user        User     @relation(fields: [userId], onDelete: Cascade, references: [id])
  name        String
  description String?
  config      Json?    // parameters, timeframes
  signals     Signal[]
  backtests   BacktestResult[]
  journalEntries TradeJournal[]
  createdAt   DateTime @default(now())
  updatedAt   DateTime @updatedAt
  @@index([userId])
}

model RegimeClassification {
  id          String   @id @default(uuid())
  userId      String?
  user        User?    @relation(fields: [userId], onDelete: SetNull, references: [id])
  symbol      String?  // null = broad market
  dataSource  DataSource?
  regime      String   // e.g. TRENDING_UP, RANGING, HIGH_VOL, etc.
  startDate   DateTime
  endDate     DateTime?
  confidence  Float?
  metadata    Json?
  createdAt   DateTime @default(now())
  @@index([userId])
  @@index([symbol, startDate])
}

model BacktestResult {
  id          String   @id @default(uuid())
  strategyId  String
  strategy    Strategy @relation(fields: [strategyId], references: [id])
  startDate   DateTime
  endDate     DateTime
  metrics     Json     // winRate, sharpe, maxDrawdown, etc.
  tradesCount Int
  createdAt   DateTime @default(now())
  @@index([strategyId])
}

model TradeJournal {
  id          String   @id @default(uuid())
  userId      String
  user        User     @relation(fields: [userId], onDelete: Cascade, references: [id])
  strategyId  String?
  strategy    Strategy? @relation(fields: [strategyId], references: [id])
  orderId     String?
  order       Order?   @relation(fields: [orderId], references: [id])
  symbol      String
  dataSource  DataSource
  entryAt     DateTime
  exitAt      DateTime?
  note        String?
  outcome     String?  // WIN, LOSS, BREAKEVEN
  agentNote   String?
  createdAt   DateTime @default(now())
  updatedAt   DateTime @updatedAt
  @@index([userId])
  @@index([strategyId])
}
```

**Required schema changes:** Add `Signal`, `Strategy`, `RegimeClassification`, `BacktestResult`, `TradeJournal`; add optional relations from `User` to these (e.g. `User.signals`, `User.strategies`, `User.regimeClassifications`, `User.tradeJournals`); optionally link `Order` to `TradeJournal` (e.g. `Order.tradeJournal`) and `SymbolProfile` to `Signal`. Add enums if you use fixed regimes/outcomes.

---

## 4. Background Job Infrastructure

### Queues (Bull)

- **DATA_GATHERING_QUEUE**
  - Config: `libs/common/src/lib/config.ts` (queue name, priorities: HIGH=1, MEDIUM=mid, LOW=MAX_SAFE_INTEGER).
  - Limiter: 1 job per 4 seconds.
  - Module: `apps/api/src/services/queues/data-gathering/data-gathering.module.ts`

- **PORTFOLIO_SNAPSHOT_COMPUTATION_QUEUE**
  - Config: same lib; priorities HIGH / LOW.
  - Lock duration ~30s.
  - Module: `apps/api/src/services/queues/portfolio-snapshot/portfolio-snapshot.module.ts`

### Job processors

- **DataGatheringProcessor** (`data-gathering.processor.ts`):
  - `GATHER_ASSET_PROFILE_PROCESS_JOB_NAME`: input `{ dataSource, symbol }`; calls `dataGatheringService.gatherAssetProfiles([job.data])`.
  - `GATHER_HISTORICAL_MARKET_DATA_PROCESS_JOB_NAME`: input `{ dataSource, symbol, date, force? }`; fetches from provider, updates `MarketData` (replace if force, else updateMany).

- **PortfolioSnapshotProcessor** (`portfolio-snapshot.processor.ts`):
  - `PORTFOLIO_SNAPSHOT_PROCESS_JOB_NAME`: input `{ userId, userCurrency, filters, calculationType }`; gets orders, builds calculator, runs `computeSnapshot()`, caches in Redis.

### DataGatheringService (`data-gathering.service.ts`)

- **addJobToQueue / addJobsToQueue:** Push one or many jobs (with name + opts, e.g. priority).
- **gather7Days():** Last 7 days; currencies HIGH, then symbols with user subscription MEDIUM, rest LOW. Used by cron.
- **gatherMax():** Full history for all symbols (LOW priority).
- **gatherSymbol({ dataSource, symbol, date })**, **gatherSymbolForDate():** Single-symbol/date; HIGH priority, force.
- **gatherAssetProfiles(identifiers?):** Fetches/enhances profiles; if no args, uses active identifiers.
- **gatherSymbols({ dataGatheringItems, force?, priority }):** Maps items to historical market-data jobs; job id = `${dataSource}-${symbol}-${date}`.
- **getActiveAssetProfileIdentifiers({ maxAge? }):** Active symbols (excl. MANUAL, RAPID_API).

Internal helpers: e.g. symbols needing 7d data, currencies for 7d, earliest date (capped), etc.

### CronService (`apps/api/src/services/cron/cron.service.ts`)

- **Hourly (random minute):** If data gathering enabled, `dataGatheringService.gather7Days()`.
- **Every 12 hours:** Load exchange rates.
- **Daily 5pm:** Fear & Greed tweet (if subscription feature on).
- **Daily midnight:** Reset user analytics (if subscription on).
- **Sunday noon:** Gather asset profiles for symbols older than 60 days (LOW).

**Agent scanning loop:** Add a new cron (or a dedicated queue consumer) that runs on an interval (e.g. every 15–60 min). Each run: dequeue or generate “scan” jobs (e.g. per user or per watchlist), call your agent pipeline (regime detection, scanner, signal generation), then optionally write to `Signal` / `RegimeClassification` and notify. Reuse the same Redis/Bull pattern and optionally the same queue with a new job name + processor.

---

## 5. Portfolio Calculation Engine

### Main types

- **PortfolioCalculator** (abstract): `apps/api/src/app/portfolio/calculator/portfolio-calculator.ts`
  - Inputs: activities (orders), account balance items, currency, filters, userId, exchange/rate and cache services.
  - **computeSnapshot():** Builds transaction points, loads market data, computes per-symbol metrics, returns `PortfolioSnapshot`.
  - **getPerformance({ start, end }):** Returns chart (historical data items) for range.
  - **getInvestments()**, **getInvestmentsByGroup()**, **getDividendInBaseCurrency()**, **getFeesInBaseCurrency()**, **getInterestInBaseCurrency()**, **getLiabilitiesInBaseCurrency()**.

- **PortfolioCalculatorFactory:** Creates calculator by `calculationType`: MWR, ROAI, ROI, TWR. Only **RoaiPortfolioCalculator** is fully implemented; others throw “not implemented”.

### Metrics already computed (ROAI)

- **Per symbol:** currentValue(s), investment (accumulated, time-weighted), gross/net performance (absolute and %), with/without currency effect; dividends, fees, interest; performance by date ranges (1d, 1y, 5y, max, mtd, wtd, ytd, per year).
- **Portfolio-level:** total current value, total investment, total fees/interest/liabilities, aggregate performance %.

### Data structures

- **PortfolioOrder**, **TransactionPoint**, **TransactionPointSymbol** (see interfaces in `portfolio/interfaces/`).
- **TimelinePosition** (in `libs/common`): positions over time with all performance fields.
- **PortfolioSnapshot:** positions, historicalData, errors, totals (currentValue, investment, fees, etc.).

### What to add for per-strategy and per-regime attribution

- **Per-strategy:** Tag or link orders to `Strategy` (e.g. `Order.strategyId` or tags). Filter activities by strategy in a dedicated calculator or in the same calculator with strategy filter; compute same ROAI-style metrics on the filtered set. Store results in `BacktestResult` or a new “StrategyPerformance” cache/snapshot.
- **Per-regime:** Join `RegimeClassification` by symbol and date so each day has a regime. When computing performance, group or filter timeline by regime and aggregate (e.g. “performance in TRENDING_UP” vs “in RANGING”). No schema change to Order needed; regime is a separate dimension keyed by (symbol, date) or (userId, date) for broad market.

---

## 6. Authentication & Authorization

### JWT

- **Issued:** In `auth.service.ts` via `jwtService.sign({ id: user.id })` after OAuth or anonymous validation. Expiration 180 days (auth.module).
- **Validated:** `JwtStrategy` (Passport `Strategy`, name `'jwt'`). Reads `Authorization: Bearer <token>`, verifies with `JWT_SECRET_KEY`, loads user by id, checks INACTIVE if subscription enabled, updates analytics, returns user → `request.user`.

### API key

- **Header:** `Api-Key <key>` (HeaderAPIKeyStrategy).
- **Validation:** `ApiKeyService.getUserByApiKey()` hashes key (PBKDF2, 100k, SHA256), looks up DB, returns user. One key per user (create replaces).

### Authorization

- **HasPermissionGuard** reads `@HasPermission(permission)` and checks `hasPermission(user.permissions, permission)`. Used with `AuthGuard('jwt')` or `AuthGuard('api-key')`.
- Permissions: `libs/common/src/lib/permissions.ts`; roles (ADMIN, USER, DEMO) map to permission arrays.

### User context

- Controllers use `@Inject(REQUEST)` and type as `RequestWithUser`; `request.user` holds full user (and settings). No custom `@RequestUser()`; standard Nest `REQUEST` injection.

**Agent:** Use either a dedicated API key per user (created via POST `/api-keys`) or a server-side JWT (e.g. issued after validating user for “agent” scope). Send `Authorization: Bearer <jwt>` or `Api-Key <key>` on every request to portfolio, order, market-data, and symbol endpoints.

---

## 7. Configuration & Feature Flags

### ConfigurationService

**File:** `apps/api/src/services/configuration/configuration.service.ts`  
Uses **envalid** to validate env vars.

**Relevant env vars:**

- **Auth:** `JWT_SECRET_KEY`, `ACCESS_TOKEN_SALT`, `ENABLE_FEATURE_AUTH_GOOGLE`, `ENABLE_FEATURE_AUTH_OIDC`, `ENABLE_FEATURE_AUTH_TOKEN`, Google/OIDC credentials.
- **Features:** `ENABLE_FEATURE_SUBSCRIPTION`, `ENABLE_FEATURE_STATISTICS`, `ENABLE_FEATURE_READ_ONLY_MODE`, `ENABLE_FEATURE_SYSTEM_MESSAGE`, `ENABLE_FEATURE_FEAR_AND_GREED_INDEX`, `ENABLE_FEATURE_GATHER_NEW_EXCHANGE_RATES`.
- **Data:** `DATA_SOURCES`, `DATA_SOURCES_GHOSTFOLIO_DATA_PROVIDER`, `DATA_SOURCE_EXCHANGE_RATES`, `DATA_SOURCE_IMPORT`.
- **API keys (external):** `API_KEY_ALPHA_VANTAGE`, `API_KEY_COINGECKO_*`, `API_KEY_EOD_HISTORICAL_DATA`, `API_KEY_FINANCIAL_MODELING_PREP`, `API_KEY_RAPID_API`, etc.
- **Infra:** `HOST`, `PORT`, `ROOT_URL`, `REDIS_*`, `DATABASE_URL`.
- **Processing:** `PROCESSOR_GATHER_*_CONCURRENCY`, `PROCESSOR_PORTFOLIO_SNAPSHOT_COMPUTATION_*`, `CACHE_TTL`, `CACHE_QUOTES_TTL`, `MAX_CHART_ITEMS`, `REQUEST_TIMEOUT`, `MAX_ACTIVITIES_TO_IMPORT`.

### PropertyService

**File:** `apps/api/src/services/property/property.service.ts`  
DB-backed key-value (e.g. `Property` table). Keys like `PROPERTY_IS_USER_SIGNUP_ENABLED`, `PROPERTY_IS_DATA_GATHERING_ENABLED` (used by cron). Use for runtime toggles.

### Where to add agent config

- **Env (recommended):** In the same envalid schema used by ConfigurationService, add for example:
  - `ENABLE_TRADING_AGENT` (default: false)
  - `TRADING_AGENT_SCAN_INTERVAL_MINUTES` (e.g. 15 or 60)
  - `TRADING_AGENT_LLM_API_KEY` or `OPENAI_API_KEY` (or vendor-specific)
  - `TRADING_AGENT_LLM_MODEL`, `TRADING_AGENT_QUEUE_NAME` (if using a dedicated queue)
- **PropertyService:** Optional flags like `PROPERTY_IS_TRADING_AGENT_ENABLED` per instance, or store user-level agent settings in `User.settings` / a new table.

---

## 8. Frontend Extension Points (Brief)

- **Stack:** Angular; routes in `apps/client/src/app/app.routes.ts`; lazy-loaded feature modules.
- **Protected routes:** `/home`, `/portfolio`, `/account`, `/accounts`, `/admin`, `/api`, `/zen`, `/webauthn`, etc. Guard: `AuthGuard` (uses `UserService.get()`).
- **Home:** `/home` with sub-routes (overview, holdings, summary, markets, watchlist). Portfolio: `/portfolio` with activities, allocations, analysis, fire, x-ray.
- **Pattern:** Page dirs with `*-page.component.ts` and `*-page.routes.ts`; shared components in `components/`.
- **AI:** Backend has GET `/ai/prompt/:mode`; frontend has `accessAssistant` permission; no dedicated “AI page” file found—likely wired into analysis or dashboard.
- **Agent UI:** Add a new route (e.g. `/home/agent` or `/portfolio/agent`) and a page component that calls new agent endpoints (signals, regimes, journal). Alternatively, build a separate React app that uses the same API (JWT or API key) and only add a link from the Angular shell if desired.

---

## 9. Tool-to-Codebase Mapping

For each of the 7 agent tools, the exact Ghostfolio code to call or extend:

| Agent tool             | Call or extend | Specific code                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ---------------------- | -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **portfolio_analysis** | Call           | GET `/portfolio/details`, GET `/portfolio/performance`, GET `/portfolio/holdings`, GET `/portfolio/report`. Services: `PortfolioService.getDetails()`, `getPerformance()`, `getHoldings()`, `getReport()`. Data: `PortfolioCalculator.computeSnapshot()`, `PortfolioSnapshot`, `TimelinePosition`.                                                                                                                                            |
| **market_data_fetch**  | Call / extend  | `DataProviderService.getQuotes()`, `getHistorical()`, `getHistoricalRaw()`. Interface: `DataProviderInterface.getQuotes`, `getHistorical`. Models: `MarketData` (dataSource, symbol, date, marketPrice, state). Endpoints: GET `/market-data/:dataSource/:symbol`, GET `/symbol/:dataSource/:symbol`, GET `/symbol/:dataSource/:symbol/:dateString`; Ghostfolio data provider GET `/data-providers/ghostfolio/quotes`, `/historical/:symbol`. |
| **regime_detector**    | Extend / new   | Use existing market data: `MarketData` (daily OHLC via marketPrice + date), `DataProviderService.getHistorical()` or GET `/symbol/.../:dateString` for history. No built-in “regime” concept: add `RegimeClassification` model and a service/queue job that computes regime from history (your logic), then store and optionally expose via new endpoint.                                                                                     |
| **strategy_scanner**   | Call / extend  | Symbol search: `DataProviderService.search()`, GET `/symbol/lookup` (query, includeIndices). Filtering: reuse portfolio filters (accounts, tags, assetClasses, dataSource, symbol). Watchlist: GET `/watchlist` (user’s list). Extend: optional “scan criteria” API that accepts rules and returns symbols (e.g. scanner service that uses search + market data + your filters).                                                              |
| **chart_validator**    | Call           | Historical data: `DataProviderService.getHistorical()` or GET `/symbol/:dataSource/:symbol` with `includeHistoricalData`, GET `/symbol/:dataSource/:symbol/:dateString`. Data: `MarketData` table (daily close; state CLOSE/INTRADAY). No chart or TA types: agent gets time series and validates in its own layer (e.g. LLM + TA library).                                                                                                   |
| **signal_archaeology** | Extend / new   | Historical market: same as chart_validator (`MarketData`, `getHistorical`, symbol endpoints). Orders: GET `/order` (range, symbol, etc.) → `Order` + `OrderService.getOrdersForPortfolioCalculator()`. No “signals” or “trades with outcome” yet: add `Signal` and `TradeJournal`; backfill or create from orders + market data in your service.                                                                                              |
| **compliance_check**   | Call           | Positions: GET `/portfolio/holdings`, `PortfolioService.getHoldings()`. Accounts: GET `/account`, GET `/account/:id`, GET `/account/:id/balances`. Structure: `Account` (balance, currency, isExcluded, platform), `Order` (quantity, unitPrice, type, accountId). Use these to check concentration, size, account-level rules; extend with a small “compliance rules” layer if needed.                                                       |

---

## 10. Gap Analysis

### What Ghostfolio gives for free

- **Portfolio & orders:** Full CRUD on orders; portfolio details, holdings, performance (ROAI), investments, dividends, report. Timeline and transaction points; multi-account, tags, filters.
- **Market data:** Daily OHLC stored in `MarketData` (dataSource, symbol, date, marketPrice, state). Multiple data providers with unified interface; historical and quotes via service and REST (including Ghostfolio data provider API for external use).
- **Symbols:** Lookup/search, symbol profile, historical by symbol/date. Asset profile resolution and overrides.
- **Auth:** JWT and API key; user and permission model; request-scoped user for all protected routes.
- **Jobs:** Bull queues for data gathering and portfolio snapshot; cron for 7d gather, profiles, exchange rates. Clear pattern to add new jobs.
- **Config:** Central env validation and feature flags; DB-backed properties for runtime toggles.

### What to extend

- **Data providers:** Add a new provider (e.g. sentiment/options) by implementing `DataProviderInterface`, adding `DataSource`, and registering in `DataProviderModule`. No change to core engine.
- **Performance attribution:** Add strategy/regime dimensions: link orders to strategies (tag or FK), add `RegimeClassification` and join by date/symbol; run existing calculator (or a copy) with filters and persist per-strategy / per-regime metrics.
- **Data gathering:** Use existing `DataGatheringService` and queue to backfill or maintain history for new symbols your agent needs; optionally add a “agent scan” job type and cron.
- **API:** New endpoints for signals, regimes, journal, backtest results (and optionally compliance) that read/write the new Prisma models; reuse same auth and permission pattern.

### What to build from scratch

- **Regime detection:** Logic and storage. Input: existing `MarketData` (and optionally quotes). Output: write to `RegimeClassification`. No existing “regime” type.
- **Signal model and pipeline:** `Signal` (and optionally `Strategy`) schema, agent logic to produce signals, and API to list/filter/expire. No signal types in Ghostfolio today.
- **Trade journal and outcome:** `TradeJournal` (and link to `Order` if desired). Backfill “outcome” from orders + historical prices; agent can add `agentNote` and use for learning.
- **Backtest engine:** `BacktestResult` storage exists in proposal; the actual backtester (run strategy logic over history, compute metrics) is new. Reuse `MarketData` and order-like structures for simulated trades.
- **Chart/TA validation:** No TA or chart types. Agent gets time series from existing endpoints and runs its own validation (e.g. LLM + TA library) outside Ghostfolio.
- **Intraday:** `MarketData` has `state: CLOSE | INTRADAY` but the codebase is oriented to daily close. Intraday series and any higher-frequency regime/signal logic are new (new provider or new tables if you persist intraday).

### Specifics (examples)

- **MarketData:** One row per (dataSource, symbol, date) with `marketPrice` and `state`. Daily granularity is the norm. To add intraday: either a new table (e.g. `MarketDataIntraday` with timestamp or bar start) and a provider that fills it, or use INTRADAY state and conventions for bar time—no existing intraday API.
- **Performance:** ROAI is fully implemented; TWR/MWR/ROI are stubbed. Per-strategy/per-regime: filter activities by strategy/regime and reuse the same calculator flow; persist results in your own models/cache.
- **Agent config:** Add `ENABLE_TRADING_AGENT`, scan interval, and LLM keys to ConfigurationService/env; optional PropertyService or user settings for per-user agent toggles.

---

_End of report._
