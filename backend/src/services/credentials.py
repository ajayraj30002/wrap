from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.security import decrypt_secret, encrypt_secret, mask_secret
from src.db.models import Credential, Provider, Worker


async def create_credential(
    session: AsyncSession,
    *,
    provider_name: str,
    name: str,
    api_key: str,
    model: str | None,
    metadata: dict,
) -> Credential:
    provider = await _get_provider(session, provider_name)
    credential = Credential(
        provider_id=provider.id,
        name=name,
        encrypted_secret=encrypt_secret(api_key),
        masked_identifier=mask_secret(api_key),
        credential_metadata=metadata,
    )
    session.add(credential)
    await session.flush()
    credential.provider = provider
    from src.core.config import settings
    from src.services.catalog import create_default_worker_for_credential, sync_provider_catalog_for_credential

    await session.commit()
    await session.refresh(credential)

    try:
        catalog_models = await sync_provider_catalog_for_credential(
            session,
            credential,
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
        )
        await create_default_worker_for_credential(session, credential, catalog_models, requested_model=model)
        await session.commit()
    except Exception as exc:
        from src.providers.base import ProviderError
        if isinstance(exc, ProviderError):
            raise ValueError(f"{provider.display_name} credential saved, but catalog sync failed: {str(exc)} ({exc.status_code})")
        raise

    return credential


async def get_credential_secret(credential: Credential) -> str:
    return decrypt_secret(credential.encrypted_secret)


async def _get_provider(session: AsyncSession, provider_name: str) -> Provider:
    result = await session.execute(select(Provider).where(Provider.name == provider_name))
    provider = result.scalar_one_or_none()
    if provider is None:
        raise ValueError(f"Unknown provider: {provider_name}")
    return provider


def credential_to_read(credential: Credential) -> dict:
    return {
        "id": credential.id,
        "provider_id": credential.provider_id,
        "provider": credential.provider.name,
        "name": credential.name,
        "masked_identifier": credential.masked_identifier,
        "enabled": credential.enabled,
        "metadata": credential.credential_metadata,
        "last_health_status": credential.last_health_status,
        "last_health_check_at": credential.last_health_check_at,
        "created_at": credential.created_at,
        "updated_at": credential.updated_at,
    }


def worker_to_read(worker: Worker) -> dict:
    return {
        "id": worker.id,
        "provider": worker.provider.name,
        "provider_id": worker.provider_id,
        "credential_id": worker.credential_id,
        "credential_name": worker.credential.name,
        "masked_identifier": getattr(worker.credential, "masked_identifier", None),
        "model": worker.model,
        "worker_type": worker.worker_type,
        "enabled": worker.enabled,
        "health_status": worker.health_status,
        "capabilities": worker.capabilities,
        "provider_model_id": worker.provider_model_id,
        "catalog_status": worker.provider_model.status if worker.provider_model else "UNKNOWN",
        "last_used_at": worker.last_used_at,
    }
