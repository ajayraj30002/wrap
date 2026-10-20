import time
from datetime import timedelta
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Response, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from src.db.session import get_session
from src.db.models import AdminUser, AdminSession
from src.core.security import get_password_hash, verify_password, generate_random_token, hash_token, require_admin_session, utcnow

router = APIRouter()

class SetupRequest(BaseModel):
    password: str

class LoginRequest(BaseModel):
    password: str

# Simple in-memory rate limiting for login attempts
_failed_attempts: dict[str, list[float]] = {}
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 300  # 5 minutes

from src.core.config import settings

def check_rate_limit(ip: str):
    if settings.ENVIRONMENT == "development" and ip in ["127.0.0.1", "::1", "localhost", "unknown", "testclient"]:
        return
    now = time.time()
    attempts = _failed_attempts.get(ip, [])
    # Clean up old attempts
    attempts = [t for t in attempts if now - t < LOCKOUT_SECONDS]
    _failed_attempts[ip] = attempts
    
    if len(attempts) >= MAX_FAILED_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Too many failed login attempts. Please try again later."
        )

def record_failed_attempt(ip: str):
    now = time.time()
    attempts = _failed_attempts.get(ip, [])
    attempts.append(now)
    _failed_attempts[ip] = attempts


@router.get("/me")
async def get_me(db: AsyncSession = Depends(get_session)):
    # Check if setup is required
    stmt = select(func.count(AdminUser.id))
    result = await db.execute(stmt)
    count = result.scalar()
    
    return {
        "setup_required": count == 0,
        "authenticated": False # The frontend will also call /me with credentials if they exist, but we can't reliably read the cookie here without require_admin_session because it might fail and throw 401. Let's make an authenticated version.
    }

@router.get("/session")
async def check_session(session: AdminSession = Depends(require_admin_session), db: AsyncSession = Depends(get_session)):
    return {
        "setup_required": False,
        "authenticated": True
    }


@router.post("/setup")
async def setup_admin(req: SetupRequest, db: AsyncSession = Depends(get_session)):
    stmt = select(func.count(AdminUser.id))
    result = await db.execute(stmt)
    count = result.scalar()
    if count > 0:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin user already exists")
    
    if len(req.password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 8 characters")

    user = AdminUser(password_hash=get_password_hash(req.password))
    db.add(user)
    await db.commit()
    
    return {"message": "Admin user created successfully"}


@router.post("/login")
async def login(req: LoginRequest, response: Response, request_obj: Request, db: AsyncSession = Depends(get_session)):
    ip = request_obj.client.host if request_obj.client else "unknown"
    check_rate_limit(ip)

    stmt = select(AdminUser).order_by(AdminUser.created_at.desc()).limit(1)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    # We use a generic error message
    generic_error = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")

    if not user:
        record_failed_attempt(ip)
        raise generic_error

    if not verify_password(req.password, user.password_hash):
        record_failed_attempt(ip)
        raise generic_error

    # Clear failed attempts on success
    if ip in _failed_attempts:
        del _failed_attempts[ip]

    # Create session
    token = generate_random_token(64)
    hashed = hash_token(token)
    
    session_obj = AdminSession(
        session_token_hash=hashed,
        expires_at=utcnow() + timedelta(days=7)
    )
    db.add(session_obj)
    await db.commit()

    # Set cookie
    response.set_cookie(
        key="session_id",
        value=token,
        httponly=True,
        samesite="strict",
        max_age=7 * 24 * 60 * 60, # 7 days
        secure=request_obj.url.scheme == "https",
        path="/"
    )

    return {"message": "Logged in successfully"}


@router.post("/logout")
async def logout(response: Response, session: AdminSession = Depends(require_admin_session), db: AsyncSession = Depends(get_session)):
    session.revoked_at = utcnow()
    await db.commit()

    response.delete_cookie(key="session_id", path="/", httponly=True, samesite="strict", secure=True)
    return {"message": "Logged out successfully"}
