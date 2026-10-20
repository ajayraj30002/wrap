import base64
import hashlib
import secrets
from hmac import compare_digest
from datetime import datetime, timezone

from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, Request, status, Cookie
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from src.core.config import Settings, get_settings
from src.db.session import get_session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.db.models import AdminSession, GatewayApiKey

bearer_scheme = HTTPBearer(auto_error=False)

password_hash = PasswordHash((Argon2Hasher(),))

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def _fernet_key(master_key: str) -> bytes:
    digest = hashlib.sha256(master_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)

def encrypt_secret(secret: str, settings: Settings | None = None) -> str:
    fernet = Fernet(_fernet_key((settings or get_settings()).WRAP_MASTER_KEY))
    return fernet.encrypt(secret.encode("utf-8")).decode("utf-8")

def decrypt_secret(encrypted_secret: str, settings: Settings | None = None) -> str:
    fernet = Fernet(_fernet_key((settings or get_settings()).WRAP_MASTER_KEY))
    return fernet.decrypt(encrypted_secret.encode("utf-8")).decode("utf-8")

def mask_secret(secret: str) -> str:
    if len(secret) <= 8:
        return "********"
    prefix = secret[:4]
    suffix = secret[-4:]
    return f"{prefix}_{'*' * 12}{suffix}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return password_hash.hash(password)

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def generate_random_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)

async def require_admin_session(
    request: Request,
    session_id: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_session)
) -> AdminSession:
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    stmt = select(AdminSession).where(
        AdminSession.session_token_hash == hash_token(session_id),
        AdminSession.revoked_at.is_(None),
        AdminSession.expires_at > utcnow()
    ).limit(1)
    
    result = await db.execute(stmt)
    session_obj = result.scalar_one_or_none()
    
    if not session_obj:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session invalid or expired"
        )

    # Update last used
    session_obj.last_used_at = utcnow()
    await db.commit()

    return session_obj

def extract_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = None,
) -> str | None:
    """Extract and sanitize API key from Bearer token, api-key (Azure), x-api-key, or query param."""
    raw: str | None = None
    if credentials and credentials.credentials:
        raw = credentials.credentials
    else:
        auth = request.headers.get("authorization") or request.headers.get("Authorization")
        if auth:
            raw = auth[7:] if auth.lower().startswith("bearer ") else auth
        else:
            raw = (
                request.headers.get("api-key")
                or request.headers.get("x-api-key")
                or request.headers.get("x-auth-token")
                or request.query_params.get("api_key")
                or request.query_params.get("key")
            )
    if not raw:
        return None
    raw = raw.strip().strip("\"'")
    while raw.lower().startswith("bearer "):
        raw = raw[7:].strip().strip("\"'")
    return raw if raw else None


async def require_wrap_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_session)
) -> GatewayApiKey:
    api_key = extract_api_key(request, credentials)
    current_settings = get_settings()

    # 1. Master Key (Superuser Bypass)
    if api_key and compare_digest(api_key, current_settings.WRAP_MASTER_KEY):
        res = await db.execute(
            select(GatewayApiKey)
            .where(GatewayApiKey.key_hash == hash_token(current_settings.WRAP_MASTER_KEY))
            .limit(1)
        )
        master_key_obj = res.scalar_one_or_none()
        if not master_key_obj:
            res_first = await db.execute(select(GatewayApiKey).where(GatewayApiKey.enabled.is_(True)).limit(1))
            first_key = res_first.scalar_one_or_none()
            if first_key:
                return first_key
            master_key_obj = GatewayApiKey(
                name="Master Superuser Key",
                prefix="master",
                key_hash=hash_token(current_settings.WRAP_MASTER_KEY),
                worker_selection_mode="AUTO",
                routing_policy="balanced",
            )
            db.add(master_key_obj)
            await db.commit()
        return master_key_obj

    # 2. Env Bootstrap Keys (settings.api_keys from WRAP_API_KEYS)
    if api_key and any(compare_digest(api_key, env_k) for env_k in current_settings.api_keys):
        hashed_env = hash_token(api_key)
        res = await db.execute(select(GatewayApiKey).where(GatewayApiKey.key_hash == hashed_env).limit(1))
        env_key_obj = res.scalar_one_or_none()
        if env_key_obj and env_key_obj.enabled and env_key_obj.revoked_at is None:
            env_key_obj.last_used_at = utcnow()
            await db.commit()
            return env_key_obj
        elif not env_key_obj:
            env_key_obj = GatewayApiKey(
                name="Bootstrap Env Key",
                prefix=api_key[:8],
                key_hash=hashed_env,
                worker_selection_mode="AUTO",
                routing_policy="balanced",
            )
            db.add(env_key_obj)
            await db.commit()
            return env_key_obj

    # 3. Database Hashed API Key lookup
    if api_key:
        hashed = hash_token(api_key)
        stmt = select(GatewayApiKey).where(GatewayApiKey.key_hash == hashed).limit(1)
        result = await db.execute(stmt)
        key_obj = result.scalar_one_or_none()
        if key_obj and key_obj.enabled and key_obj.revoked_at is None:
            key_obj.last_used_at = utcnow()
            await db.commit()
            return key_obj

    # 4. Enterprise Resilience: Development Mode Key Matching
    # In development environment, accept truncated keys matching prefix, or dummy keys
    if current_settings.ENVIRONMENT == "development":
        if api_key and len(api_key) >= 8:
            res_pref = await db.execute(
                select(GatewayApiKey)
                .where(
                    GatewayApiKey.prefix == api_key[:8],
                    GatewayApiKey.enabled.is_(True),
                    GatewayApiKey.revoked_at.is_(None),
                )
                .limit(1)
            )
            matched_pref = res_pref.scalar_one_or_none()
            if matched_pref:
                matched_pref.last_used_at = utcnow()
                await db.commit()
                return matched_pref

        # Permissive dev-mode fallback for any local dev tools
        res_dev = await db.execute(
            select(GatewayApiKey)
            .where(GatewayApiKey.enabled.is_(True), GatewayApiKey.revoked_at.is_(None))
            .order_by(GatewayApiKey.created_at.asc())
            .limit(1)
        )
        dev_fallback = res_dev.scalar_one_or_none()
        if dev_fallback:
            dev_fallback.last_used_at = utcnow()
            await db.commit()
            return dev_fallback

    # Production & Test rejection
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"message": "Missing WRAP API key", "type": "authentication_error"}},
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": {"message": "Invalid WRAP API key", "type": "authentication_error"}},
    )

