import logging
from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Dict, Any, Optional
from app.services.cache import get_revenue_summary
from app.services.reservations import (
    MixedCurrencyError,
    PropertyNotFoundError,
    get_tenant_properties,
    to_cents,
)
from app.core.auth import authenticate_request as get_current_user
from app.models.auth import AuthenticatedUser

logger = logging.getLogger(__name__)

router = APIRouter()


def _require_tenant(current_user: AuthenticatedUser) -> str:
    # No shared "default" tenant: a user without a tenant must not see anyone's data.
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tenant assigned to this user")
    return tenant_id


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    current_user: AuthenticatedUser = Depends(get_current_user)
) -> Dict[str, Any]:

    tenant_id = _require_tenant(current_user)

    if (month is None) != (year is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="month and year must be provided together",
        )

    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id, month, year)
    except PropertyNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")
    except MixedCurrencyError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception:
        logger.exception(f"Failed to load revenue summary for {property_id} (tenant: {tenant_id})")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Revenue data temporarily unavailable",
        )

    return {
        "property_id": revenue_data['property_id'],
        # Exact decimal string rounded half-up to cents (no float conversion)
        "total_revenue": str(to_cents(revenue_data['total'])),
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count'],
        "month": month,
        "year": year,
    }


@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user: AuthenticatedUser = Depends(get_current_user)
) -> Dict[str, Any]:
    tenant_id = _require_tenant(current_user)

    try:
        properties = await get_tenant_properties(tenant_id)
    except Exception:
        logger.exception(f"Failed to load properties (tenant: {tenant_id})")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Properties temporarily unavailable",
        )

    return {"data": properties, "total": len(properties)}
