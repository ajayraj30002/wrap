import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models import Credential, Provider, ProviderModel, Worker
from src.providers.base import ProviderModel as AdapterProviderModel
from src.providers.registry import registry
from src.services.credentials import get_credential_secret

logger = logging.getLogger(__name__)

ACTIVE_MODEL_STATES = {"ACTIVE", "UNKNOWN"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def sync_provider_catalog_for_credential(
    session: AsyncSession,
    credential: Credential,
    *,
    timeout: float,
) -> list[ProviderModel]:
    adapter = registry.get(credential.provider.name)
    try:
        discovered = await adapter.list_models(api_key=await get_credential_secret(credential), timeout=timeout)
    except Exception as exc:
        await mark_catalog_stale(session, credential.provider_id)
        from src.providers.base import ProviderError
        if isinstance(exc, ProviderError):
            logger.error(
                "catalog sync failed",
                extra={
                    "provider": credential.provider.name,
                    "operation": "catalog",
                    "status_code": exc.status_code,
                    "error_type": exc.error_type,
                },
            )
            raise
        logger.exception("catalog sync failed", extra={"provider": credential.provider.name})
        return []
    discovered_models = await upsert_provider_models(session, credential.provider, discovered)
    await auto_provision_workers_for_credential(session, credential, discovered_models)
    return discovered_models


async def upsert_provider_models(
    session: AsyncSession,
    provider: Provider,
    discovered: list[AdapterProviderModel],
) -> list[ProviderModel]:
    now = _now()
    existing_result = await session.execute(select(ProviderModel).where(ProviderModel.provider_id == provider.id))
    existing = {item.external_model_id: item for item in existing_result.scalars()}
    seen: set[str] = set()
    rows: list[ProviderModel] = []
    for model in discovered:
        row = existing.get(model.external_model_id)
        if row is None:
            row = ProviderModel(
                provider_id=provider.id,
                external_model_id=model.external_model_id,
                display_name=model.display_name,
                first_seen_at=now,
            )
            session.add(row)
            existing[model.external_model_id] = row
        seen.add(model.external_model_id)
        row.display_name = model.display_name
        row.status = model.status
        row.capabilities = model.capabilities
        row.context_window = model.context_window
        row.max_output_tokens = model.max_output_tokens
        row.input_modalities = model.input_modalities
        row.output_modalities = model.output_modalities
        row.streaming = model.streaming
        row.tool_calling = model.tool_calling
        row.structured_output = model.structured_output
        row.reasoning = model.reasoning
        row.catalog_metadata = model.catalog_metadata
        row.last_seen_at = now
        row.last_verified_at = now
        row.deprecated_at = now if model.status == "DEPRECATED" and row.deprecated_at is None else row.deprecated_at
        rows.append(row)
    for model_id, row in existing.items():
        if model_id not in seen and row.status == "ACTIVE":
            row.status = "STALE"
    await session.flush()
    return rows


async def mark_catalog_stale(session: AsyncSession, provider_id: UUID, model_id: str | None = None) -> None:
    statement = select(ProviderModel).where(ProviderModel.provider_id == provider_id)
    if model_id:
        statement = statement.where(ProviderModel.external_model_id == model_id)
    result = await session.execute(statement)
    for row in result.scalars():
        if row.status == "ACTIVE":
            row.status = "STALE"
    await session.flush()


async def create_default_worker_for_credential(
    session: AsyncSession,
    credential: Credential,
    catalog_models: list[ProviderModel],
    *,
    requested_model: str | None = None,
) -> Worker:
    selectable = [item for item in catalog_models if item.status in ACTIVE_MODEL_STATES]
    selected = None
    if requested_model:
        selected = next((item for item in catalog_models if item.external_model_id == requested_model), None)
        if selected and selected.status not in ACTIVE_MODEL_STATES:
            raise ValueError(f"Model {requested_model} is not active in provider catalog")
    if selected is None and selectable:
        provider_name = credential.provider.name if getattr(credential, "provider", None) else None
        if provider_name:
            adapter = registry.get(provider_name)
            default_candidates = getattr(adapter, "default_models", ())
            for def_model in default_candidates:
                matched = next((item for item in selectable if item.external_model_id == def_model), None)
                if matched:
                    selected = matched
                    break
        if selected is None:
            excluded_patterns = [
                "guard", "whisper", "audio", "tts", "embedding", "aqa",
                "imagen", "allam", "safeguard", "medlm", "antigravity",
                "deep-research", "computer-use", "robotics", "lyria", "nano-banana"
            ]
            general = [
                item for item in selectable
                if not any(pat in item.external_model_id.lower() for pat in excluded_patterns)
            ]
            if general:
                selected = sorted(general, key=lambda item: item.external_model_id)[0]
            else:
                selected = sorted(selectable, key=lambda item: item.external_model_id)[0]
    if selected is None and requested_model:
        selected = ProviderModel(
            provider_id=credential.provider_id,
            external_model_id=requested_model,
            display_name=requested_model,
            status="UNKNOWN",
            streaming=True,
            input_modalities=["text"],
            output_modalities=["text"],
            catalog_metadata={"source": "user_requested_catalog_unavailable"},
        )
        session.add(selected)
        await session.flush()
    if selected is None:
        raise ValueError("No active provider model is available for default worker creation")
    return await create_worker_from_catalog_model(session, credential, selected)


async def create_worker_from_catalog_model(
    session: AsyncSession,
    credential: Credential,
    provider_model: ProviderModel,
) -> Worker:
    if provider_model.status not in ACTIVE_MODEL_STATES:
        raise ValueError(f"Cannot create active worker for catalog model in state {provider_model.status}")
    existing = await session.execute(
        select(Worker).where(
            Worker.credential_id == credential.id,
            Worker.provider_id == credential.provider_id,
            Worker.model == provider_model.external_model_id,
        )
    )
    worker = existing.scalar_one_or_none()
    if worker is not None:
        if worker.provider_model_id != provider_model.id:
            worker.provider_model_id = provider_model.id
        return worker
    worker = Worker(
        provider_id=credential.provider_id,
        credential_id=credential.id,
        provider_model_id=provider_model.id,
        model=provider_model.external_model_id,
        worker_type="cloud",
        capabilities={
            **provider_model.capabilities,
            "streaming": provider_model.streaming,
            "tool_calling": provider_model.tool_calling,
            "structured_output": provider_model.structured_output,
            "reasoning": provider_model.reasoning,
            "context_window": provider_model.context_window,
            "max_output_tokens": provider_model.max_output_tokens,
        },
    )
    session.add(worker)
    await session.flush()
    return worker


async def auto_provision_workers_for_credential(
    session: AsyncSession,
    credential: Credential,
    catalog_models: list[ProviderModel],
) -> list[Worker]:
    """Auto-provisions workers for active, text/chat-generation capable catalog models."""
    provisioned = []
    EXCLUDED_PATTERNS = ("whisper", "tts", "transcribe", "clip", "lyria", "robotics", "prompt-guard")

    for pm in catalog_models:
        if pm.status not in ACTIVE_MODEL_STATES:
            continue
        mid = (pm.external_model_id or "").lower()
        if any(pat in mid for pat in EXCLUDED_PATTERNS):
            continue
        try:
            w = await create_worker_from_catalog_model(session, credential, pm)
            w.enabled = True
            w.health_status = "healthy"
            provisioned.append(w)
        except Exception as e:
            logger.warning("Failed to auto-provision worker for %s on %s: %s", pm.external_model_id, credential.name, e)

    await session.flush()
    return provisioned


async def load_credential_with_provider(session: AsyncSession, credential_id: UUID) -> Credential | None:
    result = await session.execute(
        select(Credential)
        .options(selectinload(Credential.provider), selectinload(Credential.workers))
        .where(Credential.id == credential_id)
    )
    return result.scalar_one_or_none()


KNOWN_PROVIDER_MODELS: dict[str, list[AdapterProviderModel]] = {
    "groq": [
        AdapterProviderModel(
            external_model_id="llama-3.3-70b-versatile",
            display_name="Llama 3.3 70B Versatile",
            status="ACTIVE",
            context_window=131072,
            max_output_tokens=32768,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "Meta", "speed": "high"},
        ),
        AdapterProviderModel(
            external_model_id="llama-3.1-8b-instant",
            display_name="Llama 3.1 8B Instant",
            status="ACTIVE",
            context_window=131072,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "Meta", "speed": "ultra-fast"},
        ),
        AdapterProviderModel(
            external_model_id="mixtral-8x7b-32768",
            display_name="Mixtral 8x7B 32k",
            status="ACTIVE",
            context_window=32768,
            max_output_tokens=4096,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "Mistral", "speed": "fast"},
        ),
        AdapterProviderModel(
            external_model_id="gemma2-9b-it",
            display_name="Gemma 2 9B IT",
            status="ACTIVE",
            context_window=8192,
            max_output_tokens=4096,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "Google", "speed": "fast"},
        ),
        AdapterProviderModel(
            external_model_id="deepseek-r1-distill-llama-70b",
            display_name="DeepSeek R1 Distill Llama 70B",
            status="ACTIVE",
            context_window=131072,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            reasoning=True,
            catalog_metadata={"developer": "DeepSeek", "speed": "high"},
        ),
        AdapterProviderModel(
            external_model_id="qwen-2.5-32b",
            display_name="Qwen 2.5 32B",
            status="ACTIVE",
            context_window=32768,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "Alibaba", "speed": "high"},
        ),
    ],
    "cerebras": [
        AdapterProviderModel(
            external_model_id="llama3.1-8b",
            display_name="Llama 3.1 8B (WSE)",
            status="ACTIVE",
            context_window=131072,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "Meta", "speed": "wafer-scale-fast"},
        ),
        AdapterProviderModel(
            external_model_id="llama-3.3-70b",
            display_name="Llama 3.3 70B (WSE)",
            status="ACTIVE",
            context_window=131072,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "Meta", "speed": "wafer-scale-fast"},
        ),
        AdapterProviderModel(
            external_model_id="qwen-2.5-72b",
            display_name="Qwen 2.5 72B (WSE)",
            status="ACTIVE",
            context_window=32768,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "Alibaba", "speed": "wafer-scale-fast"},
        ),
    ],
    "gemini": [
        AdapterProviderModel(
            external_model_id="gemini-3.7-flash",
            display_name="Gemini 3.7 Flash",
            status="ACTIVE",
            context_window=1048576,
            max_output_tokens=65536,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "Google", "speed": "ultra-fast"},
        ),
        AdapterProviderModel(
            external_model_id="gemini-3.6-flash",
            display_name="Gemini 3.6 Flash",
            status="ACTIVE",
            context_window=1048576,
            max_output_tokens=65536,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "Google", "speed": "fast"},
        ),
        AdapterProviderModel(
            external_model_id="gemini-3.5-flash",
            display_name="Gemini 3.5 Flash",
            status="ACTIVE",
            context_window=1048576,
            max_output_tokens=65536,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "Google", "speed": "fast"},
        ),
        AdapterProviderModel(
            external_model_id="gemini-flash-lite-latest",
            display_name="Gemini Flash Lite",
            status="ACTIVE",
            context_window=1048576,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "Google", "speed": "ultra-fast"},
        ),
        AdapterProviderModel(
            external_model_id="gemini-2.0-flash",
            display_name="Gemini 2.0 Flash",
            status="ACTIVE",
            context_window=1048576,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "Google", "speed": "fast"},
        ),
        AdapterProviderModel(
            external_model_id="gemini-1.5-flash",
            display_name="Gemini 1.5 Flash",
            status="ACTIVE",
            context_window=1048576,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "Google", "speed": "fast"},
        ),
        AdapterProviderModel(
            external_model_id="gemini-1.5-pro",
            display_name="Gemini 1.5 Pro",
            status="ACTIVE",
            context_window=2097152,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "Google", "speed": "standard"},
        ),
    ],
    "openai": [
        AdapterProviderModel(
            external_model_id="gpt-4o",
            display_name="GPT-4o",
            status="ACTIVE",
            context_window=128000,
            max_output_tokens=16384,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "OpenAI", "speed": "ultra-fast"},
        ),
        AdapterProviderModel(
            external_model_id="gpt-4o-mini",
            display_name="GPT-4o Mini",
            status="ACTIVE",
            context_window=128000,
            max_output_tokens=16384,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "OpenAI", "speed": "blazing-fast"},
        ),
        AdapterProviderModel(
            external_model_id="o1",
            display_name="OpenAI o1",
            status="ACTIVE",
            context_window=200000,
            max_output_tokens=100000,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            reasoning=True,
            catalog_metadata={"developer": "OpenAI", "speed": "reasoning"},
        ),
        AdapterProviderModel(
            external_model_id="o3-mini",
            display_name="OpenAI o3 Mini",
            status="ACTIVE",
            context_window=200000,
            max_output_tokens=100000,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            reasoning=True,
            catalog_metadata={"developer": "OpenAI", "speed": "fast-reasoning"},
        ),
    ],
    "anthropic": [
        AdapterProviderModel(
            external_model_id="claude-3-7-sonnet-latest",
            display_name="Claude 3.7 Sonnet",
            status="ACTIVE",
            context_window=200000,
            max_output_tokens=64000,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            reasoning=True,
            catalog_metadata={"developer": "Anthropic", "speed": "hybrid-reasoning"},
        ),
        AdapterProviderModel(
            external_model_id="claude-3-5-sonnet-latest",
            display_name="Claude 3.5 Sonnet",
            status="ACTIVE",
            context_window=200000,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "Anthropic", "speed": "fast"},
        ),
        AdapterProviderModel(
            external_model_id="claude-3-5-haiku-latest",
            display_name="Claude 3.5 Haiku",
            status="ACTIVE",
            context_window=200000,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "Anthropic", "speed": "blazing-fast"},
        ),
    ],
    "deepseek": [
        AdapterProviderModel(
            external_model_id="deepseek-chat",
            display_name="DeepSeek V3",
            status="ACTIVE",
            context_window=64000,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "DeepSeek", "speed": "high"},
        ),
        AdapterProviderModel(
            external_model_id="deepseek-reasoner",
            display_name="DeepSeek R1",
            status="ACTIVE",
            context_window=64000,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            reasoning=True,
            catalog_metadata={"developer": "DeepSeek", "speed": "reasoning"},
        ),
    ],
    "mistral": [
        AdapterProviderModel(
            external_model_id="mistral-large-latest",
            display_name="Mistral Large",
            status="ACTIVE",
            context_window=128000,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "Mistral AI", "speed": "fast"},
        ),
        AdapterProviderModel(
            external_model_id="codestral-latest",
            display_name="Codestral",
            status="ACTIVE",
            context_window=256000,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "Mistral AI", "speed": "code-specialized"},
        ),
        AdapterProviderModel(
            external_model_id="mistral-small-latest",
            display_name="Mistral Small",
            status="ACTIVE",
            context_window=128000,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "Mistral AI", "speed": "ultra-fast"},
        ),
    ],
    "together": [
        AdapterProviderModel(
            external_model_id="meta-llama/Llama-3.3-70B-Instruct-Turbo",
            display_name="Llama 3.3 70B Turbo",
            status="ACTIVE",
            context_window=131072,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "Meta", "speed": "turbo-inference"},
        ),
        AdapterProviderModel(
            external_model_id="deepseek-ai/DeepSeek-R1",
            display_name="DeepSeek R1 (Together)",
            status="ACTIVE",
            context_window=163840,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            reasoning=True,
            catalog_metadata={"developer": "DeepSeek", "speed": "reasoning"},
        ),
    ],
    "openrouter": [
        AdapterProviderModel(
            external_model_id="auto",
            display_name="OpenRouter Auto Router",
            status="ACTIVE",
            context_window=128000,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "OpenRouter", "speed": "adaptive"},
        ),
        AdapterProviderModel(
            external_model_id="openai/gpt-4o",
            display_name="GPT-4o (OpenRouter)",
            status="ACTIVE",
            context_window=128000,
            max_output_tokens=16384,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "OpenAI", "speed": "fast"},
        ),
        AdapterProviderModel(
            external_model_id="anthropic/claude-3.5-sonnet",
            display_name="Claude 3.5 Sonnet (OpenRouter)",
            status="ACTIVE",
            context_window=200000,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "Anthropic", "speed": "fast"},
        ),
    ],
    "perplexity": [
        AdapterProviderModel(
            external_model_id="sonar",
            display_name="Perplexity Sonar",
            status="ACTIVE",
            context_window=127072,
            max_output_tokens=4096,
            streaming=True,
            tool_calling=False,
            structured_output=True,
            catalog_metadata={"developer": "Perplexity", "speed": "search-augmented"},
        ),
        AdapterProviderModel(
            external_model_id="sonar-pro",
            display_name="Perplexity Sonar Pro",
            status="ACTIVE",
            context_window=200000,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=False,
            structured_output=True,
            catalog_metadata={"developer": "Perplexity", "speed": "deep-research"},
        ),
        AdapterProviderModel(
            external_model_id="sonar-reasoning",
            display_name="Perplexity Sonar Reasoning",
            status="ACTIVE",
            context_window=127072,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=False,
            structured_output=True,
            reasoning=True,
            catalog_metadata={"developer": "Perplexity", "speed": "reasoning-search"},
        ),
    ],
    "xai": [
        AdapterProviderModel(
            external_model_id="grok-2-1212",
            display_name="Grok 2",
            status="ACTIVE",
            context_window=131072,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "xAI", "speed": "high"},
        ),
        AdapterProviderModel(
            external_model_id="grok-2-vision-1212",
            display_name="Grok 2 Vision",
            status="ACTIVE",
            context_window=32768,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "xAI", "speed": "multimodal"},
        ),
    ],
    "fireworks": [
        AdapterProviderModel(
            external_model_id="accounts/fireworks/models/llama-v3p3-70b-instruct",
            display_name="Llama 3.3 70B (Fireworks)",
            status="ACTIVE",
            context_window=131072,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "Meta", "speed": "ultra-fast"},
        ),
        AdapterProviderModel(
            external_model_id="accounts/fireworks/models/deepseek-r1",
            display_name="DeepSeek R1 (Fireworks)",
            status="ACTIVE",
            context_window=163840,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            reasoning=True,
            catalog_metadata={"developer": "DeepSeek", "speed": "reasoning"},
        ),
    ],
    "sambanova": [
        AdapterProviderModel(
            external_model_id="Meta-Llama-3.3-70B-Instruct",
            display_name="Llama 3.3 70B (SambaNova)",
            status="ACTIVE",
            context_window=131072,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "Meta", "speed": "reconfigurable-dataflow"},
        ),
        AdapterProviderModel(
            external_model_id="DeepSeek-R1",
            display_name="DeepSeek R1 (SambaNova)",
            status="ACTIVE",
            context_window=131072,
            max_output_tokens=8192,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            reasoning=True,
            catalog_metadata={"developer": "DeepSeek", "speed": "dataflow-reasoning"},
        ),
    ],
    "cohere": [
        AdapterProviderModel(
            external_model_id="command-r-plus-08-2024",
            display_name="Command R+",
            status="ACTIVE",
            context_window=128000,
            max_output_tokens=4096,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "Cohere", "speed": "enterprise-fast"},
        ),
        AdapterProviderModel(
            external_model_id="command-r-08-2024",
            display_name="Command R",
            status="ACTIVE",
            context_window=128000,
            max_output_tokens=4096,
            streaming=True,
            tool_calling=True,
            structured_output=True,
            catalog_metadata={"developer": "Cohere", "speed": "enterprise-fast"},
        ),
    ],
}


async def sync_all_provider_catalogs(session: AsyncSession, *, timeout: float = 10.0) -> dict:
    providers = (await session.execute(select(Provider).where(Provider.enabled.is_(True)))).scalars().all()
    synced_providers = 0
    total_models = 0

    for provider in providers:
        creds = (await session.execute(
            select(Credential).where(Credential.provider_id == provider.id, Credential.enabled.is_(True))
        )).scalars().all()

        discovered = []
        if creds:
            for cred in creds:
                try:
                    cred.provider = provider
                    discovered = await sync_provider_catalog_for_credential(session, cred, timeout=timeout)
                    if discovered:
                        break
                except Exception as exc:
                    logger.warning("Live catalog sync failed for provider %s: %s", provider.name, exc)

        if not discovered:
            known = KNOWN_PROVIDER_MODELS.get(provider.name, [])
            if known:
                discovered = await upsert_provider_models(session, provider, known)

        if discovered:
            synced_providers += 1
            total_models += len(discovered)
            if creds:
                for cred in creds:
                    cred.provider = provider
                    try:
                        await create_default_worker_for_credential(session, cred, discovered)
                    except Exception as exc:
                        logger.warning("Could not create default worker for %s: %s", provider.name, exc)

    return {
        "status": "synced",
        "providers_synced": synced_providers,
        "total_models": total_models,
    }

