import json
import logging
import redis.asyncio as redis
from typing import Dict, Any, Optional
import os

logger = logging.getLogger(__name__)

# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

CACHE_TTL_SECONDS = 300


def _revenue_cache_key(property_id: str, tenant_id: str, month: Optional[int], year: Optional[int]) -> str:
    # Property IDs are only unique per tenant, so the tenant (and the period) must be part of the key.
    period = f"{year}-{month:02d}" if month and year else "all"
    return f"revenue:{tenant_id}:{property_id}:{period}"


async def get_revenue_summary(
    property_id: str, tenant_id: str, month: Optional[int] = None, year: Optional[int] = None
) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.
    """
    cache_key = _revenue_cache_key(property_id, tenant_id, month, year)

    # Try to get from cache
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            data = json.loads(cached)
            # Defence in depth: never serve another tenant's entry
            if data.get("tenant_id") == tenant_id:
                return data
    except Exception as e:
        logger.warning(f"Revenue cache read failed for {cache_key}: {e}")

    # Revenue calculation is delegated to the reservation service.
    from app.services.reservations import calculate_total_revenue

    # Calculate revenue (errors propagate, so failures are never cached)
    result = await calculate_total_revenue(property_id, tenant_id, month, year)

    # Cache the result for 5 minutes
    try:
        await redis_client.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(result, default=str))
    except Exception as e:
        logger.warning(f"Revenue cache write failed for {cache_key}: {e}")

    return result
