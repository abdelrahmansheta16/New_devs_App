import logging
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional, Tuple

import pytz
from sqlalchemy import text

from app.core.database_pool import db_pool

logger = logging.getLogger(__name__)

CENTS = Decimal("0.01")


class PropertyNotFoundError(Exception):
    """The property does not exist for the given tenant."""


class MixedCurrencyError(Exception):
    """Reservations in different currencies cannot be summed into one total."""


def to_cents(amount: Any) -> Decimal:
    """
    Rounds a money amount to cents (half-up). Apply once to the final sum,
    never per reservation and never through float.
    """
    return Decimal(str(amount if amount is not None else 0)).quantize(CENTS, rounding=ROUND_HALF_UP)


def month_bounds(year: int, month: int, timezone: str) -> Tuple[datetime, datetime]:
    """
    Start (inclusive) and end (exclusive) of a calendar month in the property's
    local timezone, as timezone-aware datetimes.
    """
    tz = pytz.timezone(timezone)
    start_date = tz.localize(datetime(year, month, 1))
    if month < 12:
        end_date = tz.localize(datetime(year, month + 1, 1))
    else:
        end_date = tz.localize(datetime(year + 1, 1, 1))
    return start_date, end_date


async def _get_property_timezone(session, property_id: str, tenant_id: str) -> str:
    """
    Looks up the property's timezone. Property IDs are only unique per tenant
    (prop-001 exists for two clients), so this always filters on both and
    doubles as the ownership check.
    """
    query = text("""
        SELECT timezone
        FROM properties
        WHERE id = :property_id AND tenant_id = :tenant_id
    """)
    result = await session.execute(query, {"property_id": property_id, "tenant_id": tenant_id})
    row = result.fetchone()
    if row is None:
        raise PropertyNotFoundError(property_id)
    return row.timezone


async def calculate_monthly_revenue(
    session, property_id: str, tenant_id: str, month: int, year: int, timezone: str
) -> Dict[str, Any]:
    """
    Calculates revenue for a specific month. Month boundaries are midnight in the
    property's own timezone (a check-in at 2024-02-29 23:30 UTC is March 1st in Paris).
    """
    start_date, end_date = month_bounds(year, month, timezone)

    logger.debug(f"Querying revenue for {property_id} (tenant: {tenant_id}) from {start_date} to {end_date}")

    query = text("""
        SELECT
            COALESCE(SUM(total_amount), 0) AS total_revenue,
            COUNT(*) AS reservation_count,
            MIN(currency) AS currency,
            COUNT(DISTINCT currency) AS currency_count
        FROM reservations
        WHERE property_id = :property_id
        AND tenant_id = :tenant_id
        AND check_in_date >= :start_date
        AND check_in_date < :end_date
    """)

    result = await session.execute(query, {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "start_date": start_date,
        "end_date": end_date,
    })
    row = result.fetchone()
    return {
        "total": row.total_revenue,
        "count": row.reservation_count,
        "currency": row.currency,
        "currency_count": row.currency_count,
    }


async def _calculate_all_time_revenue(session, property_id: str, tenant_id: str) -> Dict[str, Any]:
    query = text("""
        SELECT
            property_id,
            SUM(total_amount) as total_revenue,
            COUNT(*) as reservation_count,
            MIN(currency) as currency,
            COUNT(DISTINCT currency) as currency_count
        FROM reservations
        WHERE property_id = :property_id AND tenant_id = :tenant_id
        GROUP BY property_id
    """)

    result = await session.execute(query, {
        "property_id": property_id,
        "tenant_id": tenant_id
    })
    row = result.fetchone()

    if not row:
        # No reservations found for this property
        return {"total": Decimal("0"), "count": 0, "currency": None, "currency_count": 0}

    return {
        "total": row.total_revenue,
        "count": row.reservation_count,
        "currency": row.currency,
        "currency_count": row.currency_count,
    }


async def calculate_total_revenue(
    property_id: str, tenant_id: str, month: Optional[int] = None, year: Optional[int] = None
) -> Dict[str, Any]:
    """
    Aggregates revenue from database for one of the tenant's properties:
    all-time, or a single month (in the property's timezone) when month/year are given.
    """
    try:
        await db_pool.initialize()

        async with db_pool.get_session() as session:
            timezone = await _get_property_timezone(session, property_id, tenant_id)

            if month and year:
                summary = await calculate_monthly_revenue(session, property_id, tenant_id, month, year, timezone)
            else:
                summary = await _calculate_all_time_revenue(session, property_id, tenant_id)

    except PropertyNotFoundError:
        raise
    except Exception:
        # No fallback figures: the old mock data was keyed only by property_id and
        # showed one client's revenue to another. Fail loudly instead.
        logger.exception(f"Revenue query failed for {property_id} (tenant: {tenant_id})")
        raise

    if summary["currency_count"] > 1:
        raise MixedCurrencyError(f"{property_id} has reservations in multiple currencies")

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": str(to_cents(summary["total"])),
        "currency": summary["currency"] or "USD",
        "count": summary["count"],
        "month": month,
        "year": year,
    }


async def get_tenant_properties(tenant_id: str) -> List[Dict[str, Any]]:
    """
    Lists the properties that belong to a tenant.
    """
    await db_pool.initialize()

    async with db_pool.get_session() as session:
        query = text("""
            SELECT id, name, timezone
            FROM properties
            WHERE tenant_id = :tenant_id
            ORDER BY id
        """)
        result = await session.execute(query, {"tenant_id": tenant_id})
        return [
            {"id": row.id, "name": row.name, "timezone": row.timezone}
            for row in result.fetchall()
        ]
