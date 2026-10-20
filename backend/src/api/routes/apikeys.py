from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from src.db.session import get_session
from src.db.models import GatewayApiKey, AdminSession, RequestMetric
from src.core.security import generate_random_token, hash_token, require_admin_session, utcnow, encrypt_secret, decrypt_secret
from src.core.config import settings
from src.services.budget import spend_velocity_tracker
import uuid

router = APIRouter()

class CreateApiKeyRequest(BaseModel):
    name: str
    worker_selection_mode: str = "AUTO"  # AUTO, MODEL_GROUPS, WORKER_POOL, SPECIFIC_WORKER
    routing_policy: str = "balanced"
    specific_worker_id: uuid.UUID | None = None
    allowed_worker_ids: list[str] | None = None
    allowed_model_groups: list[str] | None = None
    rate_limit_rpm: int | None = 120
    max_budget_usd: float | None = None
    budget_reset_period: str = "monthly"  # monthly, weekly, daily, total
    budget_exceeded_action: str = "hard_cap"  # hard_cap, fallback_to_free
    spend_velocity_limit_usd: float | None = None
    spend_velocity_window_sec: int = 300

class UpdateApiKeyRequest(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    worker_selection_mode: str | None = None
    routing_policy: str | None = None
    specific_worker_id: uuid.UUID | None = None
    allowed_worker_ids: list[str] | None = None
    allowed_model_groups: list[str] | None = None
    rate_limit_rpm: int | None = None
    max_budget_usd: float | None = None
    budget_reset_period: str | None = None
    budget_exceeded_action: str | None = None
    spend_velocity_limit_usd: float | None = None
    spend_velocity_window_sec: int | None = None
    spend_usd: float | None = None

@router.post("")
async def create_api_key(req: CreateApiKeyRequest, session: AdminSession = Depends(require_admin_session), db: AsyncSession = Depends(get_session)):
    raw_secret = generate_random_token(48)
    full_key = f"wrap_{raw_secret}"
    
    hashed = hash_token(full_key)
    prefix = full_key[:8] # store first 8 chars for easier identification
    
    key_obj = GatewayApiKey(
        name=req.name.strip(),
        prefix=prefix,
        key_hash=hashed,
        encrypted_key=encrypt_secret(full_key),
        worker_selection_mode=req.worker_selection_mode or "AUTO",
        routing_policy=req.routing_policy or "balanced",
        specific_worker_id=req.specific_worker_id,
        allowed_worker_ids=[str(item) for item in req.allowed_worker_ids] if req.allowed_worker_ids else None,
        allowed_model_groups=[str(item) for item in req.allowed_model_groups] if req.allowed_model_groups else None,
        rate_limit_rpm=req.rate_limit_rpm or 120,
        max_budget_usd=req.max_budget_usd,
        spend_usd=0.0,
        value_saved_usd=0.0,
        budget_reset_period=req.budget_reset_period or "monthly",
        budget_exceeded_action=req.budget_exceeded_action or "hard_cap",
        spend_velocity_limit_usd=req.spend_velocity_limit_usd,
        spend_velocity_window_sec=req.spend_velocity_window_sec or 300,
    )
    db.add(key_obj)
    await db.commit()
    await db.refresh(key_obj)

    # We return the full key and masked key
    return {
        "id": key_obj.id,
        "name": key_obj.name,
        "key": full_key,
        "full_key": full_key,
        "masked_key": f"{key_obj.prefix}************",
        "worker_selection_mode": key_obj.worker_selection_mode,
        "routing_policy": key_obj.routing_policy,
        "allowed_worker_ids": key_obj.allowed_worker_ids or [],
        "allowed_model_groups": key_obj.allowed_model_groups or [],
        "rate_limit_rpm": key_obj.rate_limit_rpm or 120,
        "max_budget_usd": key_obj.max_budget_usd,
        "spend_usd": key_obj.spend_usd or 0.0,
        "value_saved_usd": key_obj.value_saved_usd or 0.0,
        "budget_reset_period": key_obj.budget_reset_period or "monthly",
        "budget_exceeded_action": key_obj.budget_exceeded_action or "hard_cap",
        "spend_velocity_limit_usd": key_obj.spend_velocity_limit_usd,
        "spend_velocity_window_sec": key_obj.spend_velocity_window_sec or 300,
        "created_at": key_obj.created_at
    }


@router.get("")
async def list_api_keys(session: AdminSession = Depends(require_admin_session), db: AsyncSession = Depends(get_session)):
    stmt = select(GatewayApiKey).order_by(GatewayApiKey.created_at.desc())
    result = await db.execute(stmt)
    keys = result.scalars().all()
    
    if not keys:
        return []

    # Reconcile metrics with recorded request metrics to guarantee ground-truth accuracy
    key_ids = [k.id for k in keys]
    rm_stmt = (
        select(
            RequestMetric.gateway_key_id,
            func.coalesce(func.sum(RequestMetric.cost_usd), 0.0).label("spend"),
            func.coalesce(func.sum(RequestMetric.value_saved_usd), 0.0).label("saved"),
        )
        .where(RequestMetric.gateway_key_id.in_(key_ids))
        .group_by(RequestMetric.gateway_key_id)
    )
    rm_res = (await db.execute(rm_stmt)).all()
    rm_map = {row.gateway_key_id: (float(row.spend or 0.0), float(row.saved or 0.0)) for row in rm_res}
    
    out_keys = []
    has_backfill = False
    for k in keys:
        raw_key = None
        if k.encrypted_key:
            try:
                raw_key = decrypt_secret(k.encrypted_key)
            except Exception:
                pass
        if not raw_key:
            for bk in settings.api_keys:
                if hash_token(bk) == k.key_hash:
                    raw_key = bk
                    k.encrypted_key = encrypt_secret(bk)
                    has_backfill = True
                    break

        out_keys.append({
            "id": k.id,
            "name": k.name,
            "prefix": k.prefix,
            "key": raw_key,
            "full_key": raw_key,
            "masked_key": f"{k.prefix}************",
            "has_full_key": raw_key is not None,
            "enabled": k.enabled,
            "created_at": k.created_at,
            "last_used_at": k.last_used_at,
            "revoked_at": k.revoked_at,
            "status": "revoked" if k.revoked_at else ("active" if k.enabled else "disabled"),
            "worker_selection_mode": k.worker_selection_mode or "AUTO",
            "routing_policy": k.routing_policy or "balanced",
            "specific_worker_id": k.specific_worker_id,
            "allowed_worker_ids": k.allowed_worker_ids or [],
            "allowed_model_groups": k.allowed_model_groups or [],
            "rate_limit_rpm": k.rate_limit_rpm or 120,
            "max_budget_usd": k.max_budget_usd,
            "spend_usd": round(max(k.spend_usd or 0.0, rm_map.get(k.id, (0.0, 0.0))[0]), 4),
            "value_saved_usd": round(max(k.value_saved_usd or 0.0, rm_map.get(k.id, (0.0, 0.0))[1]), 4),
            "budget_reset_period": k.budget_reset_period or "monthly",
            "budget_exceeded_action": k.budget_exceeded_action or "hard_cap",
            "spend_velocity_limit_usd": k.spend_velocity_limit_usd,
            "spend_velocity_window_sec": k.spend_velocity_window_sec or 300,
        })
    
    if has_backfill:
        try:
            await db.commit()
        except Exception:
            pass

    return out_keys


@router.get("/{key_id}/reveal")
async def reveal_api_key(
    key_id: uuid.UUID,
    session: AdminSession = Depends(require_admin_session),
    db: AsyncSession = Depends(get_session)
):
    stmt = select(GatewayApiKey).where(GatewayApiKey.id == key_id)
    result = await db.execute(stmt)
    key_obj = result.scalar_one_or_none()
    if not key_obj:
        raise HTTPException(status_code=404, detail="Key not found")
    
    raw_key = None
    if key_obj.encrypted_key:
        try:
            raw_key = decrypt_secret(key_obj.encrypted_key)
        except Exception:
            pass
    if not raw_key:
        for bk in settings.api_keys:
            if hash_token(bk) == key_obj.key_hash:
                raw_key = bk
                key_obj.encrypted_key = encrypt_secret(bk)
                await db.commit()
                break
    if not raw_key:
        raise HTTPException(
            status_code=400,
            detail="This legacy key was created before secret encryption was configured. Please roll the key to generate a full secret.",
        )
    return {"id": key_obj.id, "name": key_obj.name, "key": raw_key}


@router.post("/{key_id}/roll")
async def roll_api_key(
    key_id: uuid.UUID,
    session: AdminSession = Depends(require_admin_session),
    db: AsyncSession = Depends(get_session)
):
    stmt = select(GatewayApiKey).where(GatewayApiKey.id == key_id)
    result = await db.execute(stmt)
    key_obj = result.scalar_one_or_none()
    if not key_obj:
        raise HTTPException(status_code=404, detail="Key not found")
    if key_obj.revoked_at is not None:
        raise HTTPException(status_code=400, detail="Cannot roll a revoked key")

    raw_secret = generate_random_token(48)
    full_key = f"wrap_{raw_secret}"
    key_obj.key_hash = hash_token(full_key)
    key_obj.prefix = full_key[:8]
    key_obj.encrypted_key = encrypt_secret(full_key)
    await db.commit()
    await db.refresh(key_obj)

    return {
        "id": key_obj.id,
        "name": key_obj.name,
        "key": full_key,
        "full_key": full_key,
        "masked_key": f"{key_obj.prefix}************",
        "message": "Key successfully regenerated with a new secret.",
    }


@router.patch("/{key_id}")
async def update_api_key(
    key_id: uuid.UUID,
    req: UpdateApiKeyRequest,
    session: AdminSession = Depends(require_admin_session),
    db: AsyncSession = Depends(get_session)
):
    stmt = select(GatewayApiKey).where(GatewayApiKey.id == key_id)
    result = await db.execute(stmt)
    key_obj = result.scalar_one_or_none()
    
    if not key_obj:
        raise HTTPException(status_code=404, detail="Key not found")
        
    if key_obj.revoked_at is not None:
        raise HTTPException(status_code=400, detail="Cannot modify a revoked key")
        
    if req.name is not None:
        key_obj.name = req.name.strip()
    if req.enabled is not None:
        key_obj.enabled = req.enabled
    if req.worker_selection_mode is not None:
        key_obj.worker_selection_mode = req.worker_selection_mode
    if req.routing_policy is not None:
        key_obj.routing_policy = req.routing_policy
    if req.specific_worker_id is not None or req.worker_selection_mode == "SPECIFIC_WORKER":
        key_obj.specific_worker_id = req.specific_worker_id
    if req.allowed_worker_ids is not None:
        key_obj.allowed_worker_ids = [str(item) for item in req.allowed_worker_ids]
    if req.allowed_model_groups is not None:
        key_obj.allowed_model_groups = [str(item) for item in req.allowed_model_groups]
    if req.rate_limit_rpm is not None:
        key_obj.rate_limit_rpm = req.rate_limit_rpm
    if req.max_budget_usd is not None:
        key_obj.max_budget_usd = req.max_budget_usd
    if req.budget_reset_period is not None:
        key_obj.budget_reset_period = req.budget_reset_period
    if req.budget_exceeded_action is not None:
        key_obj.budget_exceeded_action = req.budget_exceeded_action
    if req.spend_velocity_limit_usd is not None:
        key_obj.spend_velocity_limit_usd = req.spend_velocity_limit_usd
    if req.spend_velocity_window_sec is not None:
        key_obj.spend_velocity_window_sec = req.spend_velocity_window_sec
    if req.spend_usd is not None:
        key_obj.spend_usd = req.spend_usd
        spend_velocity_tracker.reset_key(str(key_obj.id))
        
    await db.commit()
    await db.refresh(key_obj)
    
    return {
        "message": "Key updated successfully",
        "key": {
            "id": key_obj.id,
            "name": key_obj.name,
            "masked_key": f"{key_obj.prefix}************",
            "enabled": key_obj.enabled,
            "created_at": key_obj.created_at,
            "last_used_at": key_obj.last_used_at,
            "revoked_at": key_obj.revoked_at,
            "status": "revoked" if key_obj.revoked_at else ("active" if key_obj.enabled else "disabled"),
            "worker_selection_mode": key_obj.worker_selection_mode or "AUTO",
            "routing_policy": key_obj.routing_policy or "balanced",
            "specific_worker_id": key_obj.specific_worker_id,
            "allowed_worker_ids": key_obj.allowed_worker_ids or [],
            "allowed_model_groups": key_obj.allowed_model_groups or [],
            "rate_limit_rpm": key_obj.rate_limit_rpm or 120,
            "max_budget_usd": key_obj.max_budget_usd,
            "spend_usd": round(key_obj.spend_usd or 0.0, 4),
            "value_saved_usd": round(key_obj.value_saved_usd or 0.0, 4),
            "budget_reset_period": key_obj.budget_reset_period or "monthly",
            "budget_exceeded_action": key_obj.budget_exceeded_action or "hard_cap",
            "spend_velocity_limit_usd": key_obj.spend_velocity_limit_usd,
            "spend_velocity_window_sec": key_obj.spend_velocity_window_sec or 300,
        }
    }


@router.post("/{key_id}/reset-spend")
async def reset_key_spend(
    key_id: uuid.UUID,
    session: AdminSession = Depends(require_admin_session),
    db: AsyncSession = Depends(get_session)
):
    stmt = select(GatewayApiKey).where(GatewayApiKey.id == key_id)
    result = await db.execute(stmt)
    key_obj = result.scalar_one_or_none()
    
    if not key_obj:
        raise HTTPException(status_code=404, detail="Key not found")
        
    key_obj.spend_usd = 0.0
    spend_velocity_tracker.reset_key(str(key_obj.id))
    await db.commit()
    await db.refresh(key_obj)
    
    return {
        "message": "Key spend reset to $0.00",
        "key_id": key_obj.id,
        "spend_usd": 0.0
    }


@router.delete("/{key_id}")
async def delete_or_revoke_api_key(
    key_id: uuid.UUID,
    permanent: bool = False,
    session: AdminSession = Depends(require_admin_session),
    db: AsyncSession = Depends(get_session)
):
    stmt = select(GatewayApiKey).where(GatewayApiKey.id == key_id)
    result = await db.execute(stmt)
    key_obj = result.scalar_one_or_none()
    
    if not key_obj:
        raise HTTPException(status_code=404, detail="Key not found")
        
    if permanent or key_obj.revoked_at is not None:
        await db.delete(key_obj)
        await db.commit()
        return {"message": "Key permanently deleted", "action": "deleted"}
        
    key_obj.revoked_at = utcnow()
    key_obj.enabled = False
    await db.commit()
    
    return {"message": "Key revoked", "action": "revoked"}
