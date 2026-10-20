from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.security import hash_token
from src.db.models import GatewayApiKey, Provider
from src.providers.registry import registry


async def ensure_builtin_providers(session: AsyncSession) -> None:
    for adapter in registry.all():
        result = await session.execute(select(Provider).where(Provider.name == adapter.name))
        provider = result.scalar_one_or_none()
        metadata = {
            "default_models": list(getattr(adapter, "default_models", [])),
            "capabilities": adapter.capabilities.__dict__,
        }
        if provider is None:
            session.add(
                Provider(
                    name=adapter.name,
                    display_name=adapter.display_name,
                    provider_metadata=metadata,
                )
            )
        else:
            provider.display_name = adapter.display_name
            provider.provider_metadata = metadata
    await session.commit()


async def ensure_bootstrap_gateway_keys(session: AsyncSession) -> None:
    from src.core.security import encrypt_secret
    for raw_key in settings.api_keys:
        hashed = hash_token(raw_key)
        result = await session.execute(select(GatewayApiKey).where(GatewayApiKey.key_hash == hashed))
        existing = result.scalar_one_or_none()
        if existing is None:
            session.add(
                GatewayApiKey(
                    name="Bootstrap key",
                    prefix=raw_key[:8],
                    key_hash=hashed,
                    encrypted_key=encrypt_secret(raw_key),
                    worker_selection_mode="AUTO",
                    routing_policy="balanced",
                )
            )
        elif not existing.encrypted_key:
            existing.encrypted_key = encrypt_secret(raw_key)
    await session.commit()


