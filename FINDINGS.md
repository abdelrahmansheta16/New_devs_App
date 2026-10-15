# Revenue Dashboard: Findings and Fixes

Quick check after `docker compose up --build`:

```bash
./scripts/verify_fixes.sh   # 19 checks: totals, timezone, tenant isolation, auth
```

## TL;DR

| Report | Root cause | Fix |
|---|---|---|
| **Client A**: March totals don't match | 1. The DB was never queried; every request returned **hardcoded mock numbers**. 2. Month boundaries were computed in UTC, not the property's timezone. | Fixed the DB pool. Removed the mock fallback. Month boundaries now use the property's timezone. |
| **Client B**: other company's revenue on refresh | 1. Redis key `revenue:{property_id}` had **no tenant**, and `prop-001` exists for both clients. 2. The mock fallback was keyed by property only. 3. The dropdown hardcoded **all clients' properties**. | Key is now `revenue:{tenant}:{property}:{period}`. Property lookup requires `(id, tenant_id)`. New tenant-scoped `/dashboard/properties`. |
| **Finance**: off by a few cents | Sub-cent `NUMERIC(10,3)` sums were sent as `float` and rounded in the browser with `Math.round(x*100)/100`, which rounds x.xx5 down about 6.6% of the time. | Sum exact Decimals in SQL, round **once** with `ROUND_HALF_UP`, send as a string, and format without float math. |

## Before vs after (live API, seed data)

| Request | Before | After |
|---|---|---|
| Sunset prop-001 (Beach House Alpha) | `1000.0`, 3 bookings | **`"2250.00"`, 4 bookings** |
| Sunset prop-001, February 2024 | n/a (UTC logic: 1250.00 / 1) | `"0.00"`, 0 |
| Ocean prop-001 (Mountain Lodge Beta) | `1000.0`, 3 (**Sunset's numbers**) | **`"0.00"`, 0** |
| Ocean prop-002 (Sunset's property) | `4975.5` (**Sunset's revenue**) | **404** |
| Sunset prop-004 (Ocean's property) | `1776.5` (**Ocean's revenue**) | **404** |
| Ocean dropdown | All 5 properties, prop-001 labelled "Beach House Alpha" | Mountain Lodge Beta, Lakeside Cottage, Urban Loft Modern |
| `Authorization: Bearer mock-token-123` | 200 with Sunset's revenue | **401** |
| Redis keys | `revenue:prop-001` (shared) | `revenue:tenant-b:prop-001:all` |

Backend log before the fix, on every request:

```
ERROR:app.core.database_pool:❌ Database pool initialization failed: 'Settings' object has no attribute 'supabase_db_user'
Database error for prop-001 (tenant: tenant-a): The SQLAlchemy asyncio module requires that the Python 'greenlet' library is installed.
```

## Bug details

### 1. Revenue never came from the database (Client A + Client B)
**How found:** both clients got identical numbers, and the backend log showed `Database pool initialization failed`.

`backend/app/core/database_pool.py` failed in four stacked ways, each swallowed by a broad `except`:
1. It read `settings.supabase_db_user/...`, which don't exist on `Settings`; only `DATABASE_URL` does.
2. `poolclass=QueuePool` is rejected by async engines, and the URL lacked `+asyncpg`.
3. `get_session()` was `async def`, but callers used it as `async with db_pool.get_session()`.
4. `requirements.txt` had `sqlalchemy>=2.0.0`, which now resolves to 2.1.x. That version no longer installs `greenlet`, so the async engine can't run.

`calculate_total_revenue` then caught the exception and returned **hardcoded mock data keyed only by `property_id`**. Those mock values are real per-client sums, so each client saw the other's revenue for the other's property ids. The prop-001 mock (`1000.00`, 3) is Sunset's March total computed in UTC.

**Fix:**
- Build the async URL from `DATABASE_URL`, use the default async pool, make `initialize()` idempotent, and initialize once in the app lifespan.
- `sqlalchemy[asyncio]` in requirements.
- **No mock fallback**: errors are logged and become HTTP 503, never fabricated numbers.

### 2. Timezone: March boundaries in UTC (Client A)
`res-tz-1` checks in at `2024-02-29 23:30 UTC`, which is **March 1, 00:30 in Paris** (Beach House Alpha's timezone). `calculate_monthly_revenue` used naive `datetime(year, month, 1)` (UTC) boundaries, so this 1,250.00 booking fell into February. It also had no `tenant_id` parameter, used `$n` placeholders, and returned a placeholder `0`.

**Fix:** month boundaries are midnight in the property's own timezone (`pytz.localize`, DST-aware: Paris March runs `+01:00 → +02:00`, New York March runs `-05:00 → -04:00`). The timezone is read from `properties` by `(id, tenant_id)`. The endpoint accepts optional `month`/`year`, and the UI has a month picker (default March 2024).

### 3. Cross-tenant cache leak (Client B: "sometimes when we refresh")
`backend/app/services/cache.py` cached under `revenue:{property_id}` for 5 minutes. Property ids are only unique **per tenant** (the `properties` PK is `(id, tenant_id)`, and `prop-001` belongs to both clients). Whichever client loaded prop-001 first in a 5-minute window decided what the other saw on refresh. This was hidden while everything returned mock data; it becomes intermittent once the DB works.

**Fix:**
- Key `revenue:{tenant_id}:{property_id}:{period}`, plus a tenant check on read.
- Failures are never cached.
- Redis errors fall through to the DB instead of returning 500.

### 4. Hardcoded property list (Client B)
`frontend/src/components/Dashboard.tsx` hardcoded all 5 properties from both clients. Ocean saw Sunset's property names (its own prop-001 was labelled "Beach House Alpha") and could request Sunset's property ids.

**Fix:** new `GET /api/v1/dashboard/properties` returns only the caller's properties. `/dashboard/summary` returns **404** for any property outside the caller's tenant.

### 5. Money precision (Finance)
`total_amount` is `NUMERIC(10,3)` (sub-cent values like `333.333`). The API returned `float(total)` unrounded, and the browser rounded with `Math.round(x * 100) / 100` on binary floats. For example, `1.005 → 1.00` and `2250.055 → 2250.05`; about 6.6% of all x.xx5 values come out one cent low. Python's `round()` and `Decimal`'s default are both banker's rounding, which has the same problem.

**Fix:**
- SQL sums at full precision; `Decimal.quantize(0.01, ROUND_HALF_UP)` runs once on the total.
- `total_revenue` is returned as an exact string (`"2250.00"`).
- The UI formats it with `Intl.NumberFormat` and no arithmetic.
- The real reservation currency is returned (it was hardcoded "USD"), and mixed currencies are rejected (422) instead of summed.

### 6. Auth hardening (found while tracing tenant resolution)
- Any token that failed HS256 verification fell back to the mock Supabase client. That client accepts the literal `mock-token-123` and **unsigned** JWTs as an admin of tenant-a. It's now rejected unless a real Supabase project is configured.
- `/auth/login` issued tokens for mock users **without checking any password**. Now 401.
- The tenant was resolved from a hardcoded email map that **defaulted unknown users to tenant-a**, and `dashboard.py` fell back to a shared `"default_tenant"`. The tenant now comes from the verified token claim (`app_metadata.tenant_id`); users without a tenant get 403.

### 7. Smaller UI fixes in `RevenueSummary.tsx`
- An error stayed on screen after later successful loads.
- Fast property switching could show a stale response.
- A meaningless `X-Simulated-Tenant: candidate` header was sent; the backend never read it.

## Files changed
- Backend: `requirements.txt`, `app/core/database_pool.py`, `app/main.py`, `app/services/reservations.py`, `app/services/cache.py`, `app/api/v1/dashboard.py`, `app/core/auth.py`, `app/core/tenant_resolver.py`, `app/api/v1/login.py`
- Frontend: `components/Dashboard.tsx`, `components/RevenueSummary.tsx`, `lib/secureApi.ts`
- `scripts/verify_fixes.sh`

## Known issues not fixed (out of scope)
- **Rapid repeated refreshes log the user out.** Several session paths clear the stored token when the `/auth/me` validation request is aborted by a page reload. A single refresh is fine.
- RLS is enabled on `properties`/`reservations` with no policies, and the backend connects as the `postgres` superuser, so RLS isn't enforced. Isolation relies on the app-level `tenant_id` filters.
- The "12%" trend badge in `RevenueSummary` is hardcoded ("fake trend indicator") and shouldn't be shown on financial figures.
- `VITE_*` variables aren't passed into the frontend Docker build (it only works through `localhost` fallbacks), and `PublicRoute`/`RootRedirect`/`AppLoadingGate` read `auth.status`, which the auth context doesn't provide.
