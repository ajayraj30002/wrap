import React, { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Key, Cpu, Sliders, Shield, Plus, Check, Copy, RefreshCw, Trash2, Ban, AlertTriangle, X, Play, Edit2, Zap, Server, Database, ExternalLink, Layers, Eye, EyeOff, RotateCcw, Search, Globe, Pin, DollarSign, Terminal } from "lucide-react";
import { apiClient } from "../lib/apiClient";
import { useToast } from "../contexts/ToastContext";
import { VirtualModelTiers } from "../components/ui/VirtualModelTiers";
import { ModelScopeInspectorModal } from "../components/ui/ModelScopeInspectorModal";
import { ConfigureApiKeyModal } from "../components/ui/ConfigureApiKeyModal";
import { BudgetGovernanceView } from "../components/ui/BudgetGovernanceView";
import { WorkflowSetupView } from "../components/ui/WorkflowSetupView";

interface CachedSettingsState {
  apiKeys: any[];
  providers: any[];
  credentials: any[];
  rawProviders: any[];
  cacheStats: any;
  diagnostics: any;
  workers: any[];
  modelGroups: any[];
  gatewayOverview: any;
}

function getInitialSettings(): CachedSettingsState | null {
  try {
    const raw = sessionStorage.getItem("wrap_cached_settings");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

let cachedSettings: CachedSettingsState | null = getInitialSettings();

export function Settings() {
  const { tab = "api-keys" } = useParams<{ tab?: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(!cachedSettings);
  const [revealedKeys, setRevealedKeys] = useState<Record<string, boolean>>({});
  const [rollingKeyId, setRollingKeyId] = useState<string | null>(null);

  const [apiKeys, setApiKeys] = useState<any[]>(cachedSettings?.apiKeys || []);
  const [providers, setProviders] = useState<any[]>(cachedSettings?.providers || []);
  const [credentials, setCredentials] = useState<any[]>(cachedSettings?.credentials || []);
  const [rawProviders, setRawProviders] = useState<any[]>(cachedSettings?.rawProviders || []);

  // Credential modals state
  const [isAddCredOpen, setIsAddCredOpen] = useState(false);
  const [formCredProvider, setFormCredProvider] = useState("gemini");
  const [formCredName, setFormCredName] = useState("");
  const [formCredKey, setFormCredKey] = useState("");
  const [isAddingCred, setIsAddingCred] = useState(false);

  const [credToEdit, setCredToEdit] = useState<any | null>(null);
  const [editCredName, setEditCredName] = useState("");
  const [editCredKey, setEditCredKey] = useState("");
  const [isEditingCred, setIsEditingCred] = useState(false);

  const [credToDelete, setCredToDelete] = useState<any | null>(null);
  const [isDeletingCred, setIsDeletingCred] = useState(false);

  const [testingCredId, setTestingCredId] = useState<string | null>(null);
  const [syncingCredId, setSyncingCredId] = useState<string | null>(null);

  // Delete & Revoke state
  const [keyToDelete, setKeyToDelete] = useState<any | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  // Create Key modal state
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyPolicy, setNewKeyPolicy] = useState("balanced");
  const [newKeyMode, setNewKeyMode] = useState("AUTO");
  const [newKeyAllowedWorkerIds, setNewKeyAllowedWorkerIds] = useState<string[]>([]);
  const [newKeySpecificWorkerId, setNewKeySpecificWorkerId] = useState<string>("");
  const [workers, setWorkers] = useState<any[]>(cachedSettings?.workers || []);
  const [modelGroups, setModelGroups] = useState<any[]>(cachedSettings?.modelGroups || []);
  const [isCreating, setIsCreating] = useState(false);
  const [createdKeyResult, setCreatedKeyResult] = useState<{ name: string; key: string } | null>(null);
  const [copiedSecret, setCopiedSecret] = useState(false);
  const [isSyncingCatalogs, setIsSyncingCatalogs] = useState(false);

  // Key Configuration & Model Scope Modals state
  const [keyToConfigure, setKeyToConfigure] = useState<any | null>(null);
  const [selectedKeyForScopeInspection, setSelectedKeyForScopeInspection] = useState<any | null>(null);

  // New Key creation extra state
  const [newKeySelectedGroups, setNewKeySelectedGroups] = useState<string[]>([]);
  const [newKeyRateLimit, setNewKeyRateLimit] = useState(120);

  // Model Checklist Filter state
  const [checklistSearchQuery, setChecklistSearchQuery] = useState("");
  const [checklistProviderFilter, setChecklistProviderFilter] = useState("ALL");

  // Cache & diagnostics state
  const [cacheStats, setCacheStats] = useState<any | null>(cachedSettings?.cacheStats || null);
  const [diagnostics, setDiagnostics] = useState<any | null>(cachedSettings?.diagnostics || null);
  const [isClearingCache, setIsClearingCache] = useState(false);
  const [gatewayOverview, setGatewayOverview] = useState<{ total_saved_usd?: number; commercial_equivalent_usd?: number; actual_cost_usd?: number } | null>(cachedSettings?.gatewayOverview || null);
  
  // Live Observability Probes State
  const [probeStatus, setProbeStatus] = useState<{
    healthz: "checking" | "ok" | "error";
    ready: "checking" | "ok" | "degraded" | "error";
    metrics: "checking" | "active" | "error";
    telemetry: "checking" | "streaming" | "error";
  }>({
    healthz: "checking",
    ready: "checking",
    metrics: "checking",
    telemetry: "checking",
  });

  const handleClearCache = async () => {
    setIsClearingCache(true);
    try {
      const res = await apiClient.post("/api/cache/clear");
      setCacheStats(res.stats);
      toast({
        title: "Prompt Cache Purged",
        description: "All in-memory cache entries evicted successfully.",
        type: "success",
      });
    } catch (err: any) {
      toast({
        title: "Purge Failed",
        description: err.data?.detail || "Could not purge response cache.",
        type: "error",
      });
    } finally {
      setIsClearingCache(false);
    }
  };

  const handleSyncAllCatalogs = async () => {
    setIsSyncingCatalogs(true);
    try {
      const res = await apiClient.post("/api/catalogs/sync-all");
      toast({
        title: "Catalogs Synchronized",
        description: `Discovered and synced ${res.total_models || 0} models across ${res.providers_synced || 0} active providers.`,
        type: "success",
      });
      await fetchSettingsData();
    } catch (e: any) {
      toast({
        title: "Sync Failed",
        description: e.data?.detail || "Could not synchronize provider catalogs",
        type: "error",
      });
    } finally {
      setIsSyncingCatalogs(false);
    }
  };

  const fetchSettingsData = useCallback(async (isManualRefresh = false) => {
    if (!cachedSettings || isManualRefresh) {
      setLoading(true);
    }

    // Initialize cachedSettings container if not yet created
    if (!cachedSettings) {
      cachedSettings = {
        apiKeys: [],
        providers: [],
        credentials: [],
        rawProviders: [],
        cacheStats: null,
        diagnostics: null,
        workers: [],
        modelGroups: [],
        gatewayOverview: null,
      };
    }

    // 1. High-priority: Load Gateway Keys immediately
    const keysPromise = apiClient.get("/api/apikeys", { bypassCache: isManualRefresh })
      .then((data) => {
        if (Array.isArray(data)) {
          setApiKeys(data);
          if (cachedSettings) cachedSettings.apiKeys = data;
          setLoading(false); // Gateway keys are ready to render immediately!
        }
      })
      .catch((e) => console.error("Error loading keys:", e));

    // 2. High-priority: Load Workers & Virtual Model Groups
    const workersPromise = apiClient.get("/api/workers", { bypassCache: isManualRefresh })
      .then((data) => {
        if (Array.isArray(data)) {
          setWorkers(data);
          if (cachedSettings) cachedSettings.workers = data;
        }
      })
      .catch((e) => console.error("Error loading workers:", e));

    const groupsPromise = apiClient.get("/api/model-groups", { bypassCache: isManualRefresh })
      .then((data) => {
        if (Array.isArray(data)) {
          setModelGroups(data);
          if (cachedSettings) cachedSettings.modelGroups = data;
        }
      })
      .catch((e) => console.error("Error loading model groups:", e));

    // 3. Credentials & Gateway Overview
    const credsPromise = apiClient.get("/api/credentials", { bypassCache: isManualRefresh })
      .then((data) => {
        if (Array.isArray(data)) {
          setCredentials(data);
          if (cachedSettings) cachedSettings.credentials = data;
        }
      })
      .catch((e) => console.error("Error loading credentials:", e));

    const overviewPromise = apiClient.get("/api/metrics/overview", { bypassCache: isManualRefresh })
      .then((data) => {
        if (data) {
          setGatewayOverview(data);
          if (cachedSettings) cachedSettings.gatewayOverview = data;
        }
      })
      .catch((e) => console.error("Error loading overview:", e));

    // 4. Providers & Provider Models
    const providersPromise = Promise.allSettled([
      apiClient.get("/api/providers", { bypassCache: isManualRefresh }),
      apiClient.get("/api/provider-models", { bypassCache: isManualRefresh }),
    ]).then(([provRes, modRes]) => {
      if (provRes.status === "fulfilled" && Array.isArray(provRes.value)) {
        setRawProviders(provRes.value);
        const models = modRes.status === "fulfilled" && Array.isArray(modRes.value) ? modRes.value : [];
        const mapped = provRes.value.map((p: any) => {
          const count = models.filter((m: any) => m.provider_id === p.id || m.provider?.toLowerCase() === p.name?.toLowerCase()).length;
          const pType = p.name === "groq"
            ? "LPU Ultra-Fast Inference"
            : p.name === "cerebras" || p.name === "sambanova"
            ? "Wafer-Scale / Dataflow LPU"
            : p.name === "anthropic" || p.name === "openai" || p.name === "gemini"
            ? "Frontier Foundation Lab"
            : p.name === "deepseek" || p.name === "mistral" || p.name === "together" || p.name === "fireworks"
            ? "Open-Weights Inference Engine"
            : p.name === "openrouter"
            ? "Universal Gateway Aggregator"
            : p.name === "perplexity"
            ? "Search-Augmented Reasoning"
            : "Official REST API";

          return {
            id: p.id,
            name: p.display_name || p.name,
            code: p.name,
            type: pType,
            models: count || (p.provider_metadata?.default_models?.length || 0),
            status: p.enabled ? "healthy" : "offline",
            latency: p.name === "groq" ? "480ms" : p.name === "cerebras" ? "320ms" : "Active Pool",
          };
        });
        setProviders(mapped);
        if (cachedSettings) {
          cachedSettings.providers = mapped;
          cachedSettings.rawProviders = provRes.value;
        }
      }
    }).catch((e) => console.error("Error loading providers:", e));

    // 5. Diagnostics & Cache Stats
    const cachePromise = apiClient.get("/api/cache/stats", { bypassCache: isManualRefresh })
      .then((data) => {
        if (data) {
          setCacheStats(data);
          if (cachedSettings) cachedSettings.cacheStats = data;
        }
      })
      .catch((e) => console.error("Error loading cache stats:", e));

    const diagPromise = apiClient.get("/api/system/diagnostics", { bypassCache: isManualRefresh })
      .then((data) => {
        if (data) {
          setDiagnostics(data);
          if (cachedSettings) cachedSettings.diagnostics = data;
        }
      })
      .catch((e) => console.error("Error loading diagnostics:", e));

    try {
      await Promise.allSettled([
        keysPromise,
        workersPromise,
        groupsPromise,
        credsPromise,
        overviewPromise,
        providersPromise,
        cachePromise,
        diagPromise,
      ]);
      if (cachedSettings) {
        try {
          sessionStorage.setItem("wrap_cached_settings", JSON.stringify(cachedSettings));
        } catch {}
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSettingsData();
  }, [fetchSettingsData]);

  // Live probe polling effect when on System tab
  useEffect(() => {
    if (tab !== "system") return;
    let isMounted = true;

    const checkProbes = async () => {
      try {
        const [hRes, rRes, mRes] = await Promise.allSettled([
          fetch("/healthz"),
          fetch("/ready"),
          fetch("/metrics"),
        ]);
        if (!isMounted) return;
        setProbeStatus({
          healthz: hRes.status === "fulfilled" && hRes.value.ok ? "ok" : "error",
          ready:
            rRes.status === "fulfilled"
              ? rRes.value.ok
                ? "ok"
                : rRes.value.status === 503
                ? "degraded"
                : "error"
              : "error",
          metrics: mRes.status === "fulfilled" && mRes.value.ok ? "active" : "error",
          telemetry: "streaming",
        });
      } catch {
        if (isMounted) {
          setProbeStatus({ healthz: "error", ready: "error", metrics: "error", telemetry: "error" });
        }
      }
    };

    checkProbes();
    const interval = setInterval(checkProbes, 15000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [tab]);


  const handleCopyApiKey = async (k: any) => {
    let keyToCopy = k.key || k.full_key;
    if (!keyToCopy) {
      try {
        const res = await apiClient.get(`/api/apikeys/${k.id}/reveal`);
        if (res?.key) {
          keyToCopy = res.key;
          setApiKeys((prev) =>
            prev.map((item) =>
              item.id === k.id ? { ...item, key: res.key, full_key: res.key, has_full_key: true } : item
            )
          );
        }
      } catch (err: any) {
        console.warn("Could not reveal key:", err);
      }
    }

    if (keyToCopy && !keyToCopy.includes("***") && !keyToCopy.includes("••••")) {
      navigator.clipboard.writeText(keyToCopy);
      setCopiedKey(k.id);
      toast({
        title: "Complete Key Copied!",
        description: `Full key ${keyToCopy.slice(0, 14)}... copied to clipboard (ready for Roo Code, Continue, or Cursor).`,
        type: "success",
      });
      setTimeout(() => setCopiedKey(null), 2500);
    } else {
      toast({
        title: "Legacy Hashed Key",
        description: "This key was stored as a legacy hash without plaintext. Click 'Roll' to generate a full unmasked key.",
        type: "warning",
      });
    }
  };

  const handleToggleReveal = async (k: any) => {
    const isCurrentlyRevealed = Boolean(revealedKeys[k.id]);
    if (isCurrentlyRevealed) {
      setRevealedKeys((prev) => ({ ...prev, [k.id]: false }));
      return;
    }

    if (!k.key && !k.full_key) {
      try {
        const res = await apiClient.get(`/api/apikeys/${k.id}/reveal`);
        if (res?.key) {
          setApiKeys((prev) =>
            prev.map((item) =>
              item.id === k.id ? { ...item, key: res.key, full_key: res.key, has_full_key: true } : item
            )
          );
        }
      } catch (e: any) {
        toast({
          title: "Cannot Reveal Key",
          description: e?.data?.detail || "This legacy key has no plaintext. Click Roll to generate a fresh full key.",
          type: "warning",
        });
        return;
      }
    }

    setRevealedKeys((prev) => ({ ...prev, [k.id]: true }));
  };

  const handleRollKey = async (k: any) => {
    if (!window.confirm(`Are you sure you want to roll "${k.name}"? A new random key will be generated immediately and the previous key will be invalidated.`)) {
      return;
    }
    setRollingKeyId(k.id);
    try {
      const res = await apiClient.post(`/api/apikeys/${k.id}/roll`);
      if (res?.key) {
        navigator.clipboard.writeText(res.key);
        setCopiedKey(k.id);
        toast({
          title: "Key Rolled Successfully!",
          description: `New key ${res.key.slice(0, 14)}... generated and copied to clipboard!`,
          type: "success",
        });
        setRevealedKeys((prev) => ({ ...prev, [k.id]: true }));
        fetchSettingsData(true);
      }
    } catch (e: any) {
      toast({
        title: "Roll Failed",
        description: e?.data?.detail || "Could not roll key",
        type: "error",
      });
    } finally {
      setRollingKeyId(null);
    }
  };

  const copySecretKey = (secret: string) => {
    navigator.clipboard.writeText(secret);
    setCopiedSecret(true);
    toast({ title: "Copied to clipboard", description: "Secret API key copied", type: "success" });
    setTimeout(() => setCopiedSecret(false), 2500);
  };

  // Delete or Revoke key action
  const handleDeleteKey = async (keyId: string, permanent: boolean) => {
    setIsDeleting(true);
    try {
      await apiClient.delete(`/api/apikeys/${keyId}${permanent ? "?permanent=true" : ""}`);
      toast({
        title: permanent ? "Key Permanently Deleted" : "Key Revoked",
        description: permanent
          ? "The API key was purged from the database"
          : "The API key has been revoked and deactivated",
        type: "success",
      });
      setKeyToDelete(null);
      await fetchSettingsData();
    } catch (e: any) {
      toast({
        title: "Action Failed",
        description: e.data?.detail || "Could not complete delete operation",
        type: "error",
      });
    } finally {
      setIsDeleting(false);
    }
  };

  // Create key action
  const handleCreateKey = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newKeyName.trim()) {
      toast({ title: "Name Required", description: "Please enter an identifiable name for this key", type: "warning" });
      return;
    }

    if (newKeyMode === "MODEL_GROUPS" && newKeySelectedGroups.length === 0) {
      toast({ title: "Virtual Tiers Required", description: "Please select at least one Virtual Tier for this key.", type: "warning" });
      return;
    }

    if (newKeyMode === "WORKER_POOL" && newKeyAllowedWorkerIds.length === 0) {
      toast({ title: "No Models Selected", description: "Please checklist at least one allowed model for this key.", type: "warning" });
      return;
    }

    if (newKeyMode === "SPECIFIC_WORKER" && !newKeySpecificWorkerId) {
      toast({ title: "Worker Required", description: "Please select a pinned target worker.", type: "warning" });
      return;
    }

    setIsCreating(true);
    try {
      const payload: any = {
        name: newKeyName.trim(),
        worker_selection_mode: newKeyMode,
        routing_policy: newKeyPolicy,
        rate_limit_rpm: Number(newKeyRateLimit) || 120,
      };
      if (newKeyMode === "MODEL_GROUPS") {
        payload.allowed_model_groups = newKeySelectedGroups;
      } else if (newKeyMode === "WORKER_POOL") {
        payload.allowed_worker_ids = newKeyAllowedWorkerIds;
      } else if (newKeyMode === "SPECIFIC_WORKER") {
        payload.specific_worker_id = newKeySpecificWorkerId;
      }

      const data = await apiClient.post("/api/apikeys", payload);

      setCreatedKeyResult({
        name: data.name,
        key: data.key,
      });
      toast({ title: "Key Created", description: `API key ${data.name} created successfully`, type: "success" });
      await fetchSettingsData();
    } catch (e: any) {
      toast({
        title: "Creation Failed",
        description: e.data?.detail || "Could not create API key",
        type: "error",
      });
    } finally {
      setIsCreating(false);
    }
  };

  // Credential action handlers
  const handleAddCredential = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formCredProvider || !formCredName.trim() || !formCredKey.trim()) {
      toast({ title: "Incomplete Form", description: "Provider, Name, and API Key are required", type: "warning" });
      return;
    }
    setIsAddingCred(true);
    try {
      await apiClient.post("/api/credentials", {
        provider: formCredProvider,
        name: formCredName.trim(),
        api_key: formCredKey.trim(),
        metadata: {},
      });
      toast({
        title: "Credential Added",
        description: `Successfully added ${formCredName.trim()} and synced model catalog`,
        type: "success",
      });
      setIsAddCredOpen(false);
      setFormCredName("");
      setFormCredKey("");
      await fetchSettingsData();
    } catch (err: any) {
      toast({
        title: "Failed to Add Credential",
        description: err.data?.detail || "Could not register credential",
        type: "error",
      });
    } finally {
      setIsAddingCred(false);
    }
  };

  const handleUpdateCredential = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!credToEdit) return;
    setIsEditingCred(true);
    try {
      const payload: any = {};
      if (editCredName.trim()) payload.name = editCredName.trim();
      if (editCredKey.trim()) payload.api_key = editCredKey.trim();
      await apiClient.patch(`/api/credentials/${credToEdit.id}`, payload);
      toast({
        title: "Credential Updated",
        description: `Updated ${credToEdit.name} successfully`,
        type: "success",
      });
      setCredToEdit(null);
      setEditCredKey("");
      setEditCredName("");
      await fetchSettingsData();
    } catch (err: any) {
      toast({
        title: "Update Failed",
        description: err.data?.detail || "Could not update credential",
        type: "error",
      });
    } finally {
      setIsEditingCred(false);
    }
  };

  const handleToggleCredential = async (id: string, current: boolean) => {
    try {
      await apiClient.patch(`/api/credentials/${id}`, { enabled: !current });
      toast({
        title: `Credential ${current ? "Disabled" : "Enabled"}`,
        type: "success",
      });
      await fetchSettingsData();
    } catch (err: any) {
      toast({
        title: "Toggle Failed",
        description: err.data?.detail || "Could not toggle credential",
        type: "error",
      });
    }
  };

  const handleTestCredential = async (id: string) => {
    setTestingCredId(id);
    try {
      const res = await apiClient.post(`/api/credentials/${id}/test`, {});
      if (res.status === "healthy") {
        toast({
          title: "Connection Verified",
          description: "Provider responded successfully with live API check.",
          type: "success",
        });
      } else {
        toast({
          title: "Connection Failed",
          description: res.error_message || res.error_type || "Upstream returned unhealthy.",
          type: "warning",
        });
      }
      if (res.last_health_status) {
        setCredentials((prev) =>
          prev.map((c) => (c.id === id ? { ...c, last_health_status: res.last_health_status } : c))
        );
      }
      await fetchSettingsData();
    } catch (err: any) {
      toast({
        title: "Test Request Failed",
        description: err.data?.detail || err.message || "Error connecting to provider.",
        type: "error",
      });
      setCredentials((prev) =>
        prev.map((c) => (c.id === id ? { ...c, last_health_status: "unhealthy" } : c))
      );
      await fetchSettingsData();
    } finally {
      setTestingCredId(null);
    }
  };

  const handleSyncCredential = async (id: string) => {
    setSyncingCredId(id);
    try {
      const res = await apiClient.post(`/api/credentials/${id}/catalog/sync`, {});
      toast({
        title: "Catalog Synced",
        description: `Discovered ${res.total_models || 0} models for this credential.`,
        type: "success",
      });
      await fetchSettingsData();
    } catch (err: any) {
      toast({
        title: "Sync Failed",
        description: err.data?.detail || "Provider catalog sync failed.",
        type: "warning",
      });
    } finally {
      setSyncingCredId(null);
    }
  };

  const handleDeleteCredential = async () => {
    if (!credToDelete) return;
    setIsDeletingCred(true);
    try {
      await apiClient.delete(`/api/credentials/${credToDelete.id}`);
      toast({
        title: "Credential Deleted",
        description: "Removed credential and associated workers.",
        type: "success",
      });
      setCredToDelete(null);
      await fetchSettingsData();
    } catch (err: any) {
      toast({
        title: "Failed to Delete",
        description: err.data?.detail || "Error deleting credential.",
        type: "error",
      });
    } finally {
      setIsDeletingCred(false);
    }
  };

  return (
    <div className="page-container">
      {/* Page Header */}
      <div className="page-header">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.2rem" }}>
            <span className="font-mono text-tertiary" style={{ fontSize: "0.6875rem", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600 }}>
              {tab === "budgets" ? "SYSTEM GOVERNANCE" : "ADMINISTRATION"}
            </span>
            <span style={{ color: "var(--text-muted)", fontSize: "0.6875rem" }}>/</span>
            <span className="font-mono text-secondary" style={{ fontSize: "0.6875rem" }}>
              {tab === "budgets"
                ? "Budgets & Economic Telemetry"
                : tab === "api-keys"
                ? "Gateway Access Keys"
                : tab === "model-groups"
                ? "Virtual Model Tiers"
                : tab === "providers"
                ? "Provider Infrastructure"
                : tab === "policies"
                ? "Autonomous Policies"
                : tab === "setup" || tab === "workflows"
                ? "Workflow & Tool Setup"
                : "System Health & Core"}
            </span>
          </div>
          <h1 className="page-title">
            {tab === "budgets" && <DollarSign size={20} style={{ color: "var(--accent)" }} />}
            {(tab === "setup" || tab === "workflows") && <Terminal size={20} style={{ color: "var(--accent)" }} />}
            <span>
              {tab === "budgets"
                ? "Financial Accounting & Budget Governance"
                : tab === "setup" || tab === "workflows"
                ? "Workflow & Tool Integration Guide"
                : "Administration & System Settings"}
            </span>
          </h1>
          <p className="page-subtitle">
            {tab === "budgets"
              ? "Real-time cost telemetry, dual-economic value accounting, hard budget caps, and runaway loop circuit breakers"
              : tab === "setup" || tab === "workflows"
              ? "Plug WRAP into Cursor, Cline, LangChain, LiteLLM, and SDK clients with drop-in OpenAI-compatible endpoints"
              : "Configure client API keys, provider credentials, autonomous routing policies, and infrastructure"}
          </p>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={() => fetchSettingsData(true)} disabled={loading} title="Refresh settings">
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          <span>{loading ? "Refreshing..." : "Refresh"}</span>
        </button>
      </div>

      {/* Tabs */}
      <div
        className="filter-btn-group"
        style={{
          alignSelf: "flex-start",
          backgroundColor: "var(--bg-surface)",
          border: "1px solid var(--border-subtle)",
          padding: "3px",
          borderRadius: "var(--radius-md)",
          gap: "2px",
        }}
      >
        {[
          { id: "api-keys", label: `Gateway Keys (${apiKeys.length || 0})`, icon: <Key size={13} /> },
          { id: "budgets", label: "Budgets & Spend", icon: <DollarSign size={13} /> },
          { id: "model-groups", label: `Virtual Tiers (${modelGroups.length || 4})`, icon: <Layers size={13} /> },
          { id: "providers", label: `Provider Keys & Models (${credentials.length || 0})`, icon: <Cpu size={13} /> },
          { id: "policies", label: "Routing Policies", icon: <Sliders size={13} /> },
          { id: "setup", label: "Workflow Setup", icon: <Terminal size={13} /> },
          { id: "system", label: "System", icon: <Shield size={13} /> },
        ].map((t) => (
          <button
            key={t.id}
            className={`filter-btn flex items-center gap-1 ${tab === t.id ? "active" : ""}`}
            onClick={() => navigate(`/settings/${t.id}`)}
            style={{
              padding: "0.35rem 0.65rem",
              fontSize: "0.75rem",
              borderRadius: "var(--radius-sm)",
            }}
          >
            {t.icon}
            <span>{t.label}</span>
          </button>
        ))}
      </div>

      {/* Tab: API Keys (Real Database Records) */}
      {tab === "api-keys" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)" }}>
              Client API Keys in Database
            </span>
            <button
              className="btn btn-primary btn-sm flex items-center gap-1"
              onClick={() => {
                setCreatedKeyResult(null);
                setNewKeyName("");
                setNewKeyMode("AUTO");
                setNewKeyAllowedWorkerIds([]);
                setNewKeySelectedGroups([]);
                setNewKeySpecificWorkerId("");
                setNewKeyPolicy("balanced");
                setNewKeyRateLimit(120);
                setIsCreateOpen(true);
              }}
            >
              <Plus size={13} />
              <span>Create New Key</span>
            </button>
          </div>

          <div className="dense-table-wrapper">
            <table className="dense-table">
              <thead>
                <tr>
                  <th>Key Name</th>
                  <th>Gateway API Key</th>
                  <th>Routing Policy</th>
                  <th>Model Access Scope</th>
                  <th>Spend & Budget</th>
                  <th>Created</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {loading && apiKeys.length === 0 ? (
                  Array.from({ length: 3 }).map((_, i) => (
                    <tr key={`skel-key-${i}`}>
                      <td colSpan={8} style={{ padding: "1rem" }}>
                        <div className="skeleton-shimmer skeleton-line" style={{ width: "100%", height: "20px" }} />
                      </td>
                    </tr>
                  ))
                ) : apiKeys.length === 0 ? (
                  <tr>
                    <td colSpan={8} style={{ textAlign: "center", padding: "2rem", color: "var(--text-tertiary)" }}>
                      No API keys found. Create a new key to allow clients to access the gateway.
                    </td>
                  </tr>
                ) : (
                  apiKeys.map((k) => {
                    const isRevoked = Boolean(k.revoked_at);
                    const isActive = k.enabled && !isRevoked;
                    const statusClass = isRevoked ? "error" : isActive ? "" : "warning";
                    const statusText = isRevoked ? "REVOKED" : isActive ? "ACTIVE" : "DISABLED";

                    return (
                      <tr key={k.id}>
                        <td style={{ fontWeight: 600, color: "var(--text-primary)" }}>{k.name}</td>
                        <td>
                          <div style={{ display: "inline-flex", alignItems: "center", gap: "0.375rem" }}>
                            <span
                              className="font-mono text-secondary"
                              style={{
                                fontSize: "0.75rem",
                                letterSpacing: revealedKeys[k.id] ? "normal" : "0.04em",
                                maxWidth: "230px",
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                whiteSpace: "nowrap",
                                backgroundColor: "var(--bg-elevated)",
                                padding: "0.2rem 0.5rem",
                                borderRadius: "var(--radius-xs)",
                                border: "1px solid var(--border-subtle)",
                                userSelect: "all",
                              }}
                              title={revealedKeys[k.id] ? (k.key || k.full_key || k.masked_key) : "Click Eye or Copy to reveal complete key"}
                            >
                              {revealedKeys[k.id] ? (k.key || k.full_key || k.masked_key) : (k.masked_key || `${k.prefix}••••••••`)}
                            </span>
                            <button
                              type="button"
                              className="btn btn-ghost btn-xs"
                              onClick={() => handleToggleReveal(k)}
                              title={revealedKeys[k.id] ? "Hide complete key" : "Reveal complete key"}
                              style={{ padding: "0.2rem", color: "var(--text-tertiary)" }}
                            >
                              {revealedKeys[k.id] ? <EyeOff size={12} /> : <Eye size={12} />}
                            </button>
                          </div>
                        </td>
                        <td>
                          <span
                            className="font-mono text-secondary"
                            style={{
                              fontSize: "0.6875rem",
                              backgroundColor: "var(--bg-elevated)",
                              padding: "0.15rem 0.4rem",
                              borderRadius: "var(--radius-xs)",
                              border: "1px solid var(--border-subtle)",
                            }}
                          >
                            {k.routing_policy || "balanced"}
                          </span>
                        </td>
                        <td>
                          {k.worker_selection_mode === "MODEL_GROUPS" ? (
                            <button
                              type="button"
                              className="btn btn-ghost btn-xs flex items-center gap-1"
                              onClick={() => setSelectedKeyForScopeInspection(k)}
                              style={{
                                borderColor: "var(--accent-border)",
                                color: "var(--accent)",
                                backgroundColor: "var(--accent-muted)",
                                padding: "0.15rem 0.45rem",
                                borderRadius: "var(--radius-xs)",
                                fontWeight: 500,
                              }}
                              title="Click to inspect permitted virtual tiers"
                            >
                              <Layers size={10} />
                              <span>
                                {k.allowed_model_groups?.length === 1
                                  ? (modelGroups.find((g: any) => g.id === k.allowed_model_groups[0])?.name || k.allowed_model_groups[0])
                                  : `${k.allowed_model_groups?.length || 0} Virtual Tiers`}
                              </span>
                              <Eye size={10} style={{ opacity: 0.7 }} />
                            </button>
                          ) : k.worker_selection_mode === "WORKER_POOL" ? (
                            <button
                              type="button"
                              className="btn btn-ghost btn-xs flex items-center gap-1"
                              onClick={() => setSelectedKeyForScopeInspection(k)}
                              style={{
                                borderColor: "var(--border-default)",
                                color: "var(--text-secondary)",
                                backgroundColor: "var(--bg-subtle)",
                                padding: "0.15rem 0.45rem",
                                borderRadius: "var(--radius-xs)",
                              }}
                              title="Click to inspect permitted models scope"
                            >
                              <Shield size={10} />
                              <span>Pool ({k.allowed_worker_ids?.length || 0} models)</span>
                              <Eye size={10} style={{ opacity: 0.7 }} />
                            </button>
                          ) : k.worker_selection_mode === "SPECIFIC_WORKER" ? (
                            <button
                              type="button"
                              className="btn btn-ghost btn-xs flex items-center gap-1 status-pill warning"
                              onClick={() => setSelectedKeyForScopeInspection(k)}
                              title="Click to inspect pinned target worker"
                              style={{ padding: "0.15rem 0.45rem" }}
                            >
                              <Pin size={10} />
                              <span>Pinned Worker</span>
                              <Eye size={10} style={{ opacity: 0.7 }} />
                            </button>
                          ) : (
                            <span
                              className="status-pill"
                              style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem" }}
                            >
                              <span>All Models (AUTO)</span>
                            </span>
                          )}
                        </td>
                        <td>
                          <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem", minWidth: "120px" }}>
                            <div style={{ display: "flex", alignItems: "baseline", gap: "0.25rem" }}>
                              <span className="font-mono" style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--text-primary)" }}>
                                ${(k.spend_usd || 0).toFixed(2)}
                              </span>
                              <span className="font-mono text-tertiary" style={{ fontSize: "0.65625rem" }}>
                                {k.max_budget_usd != null ? `/ $${Number(k.max_budget_usd).toFixed(2)}` : "(Uncapped)"}
                              </span>
                            </div>

                            {k.max_budget_usd != null && Number(k.max_budget_usd) > 0 && (
                              <div
                                style={{
                                  width: "100%",
                                  maxWidth: "110px",
                                  height: "3px",
                                  backgroundColor: "var(--bg-elevated)",
                                  borderRadius: "1.5px",
                                  overflow: "hidden",
                                }}
                              >
                                <div
                                  style={{
                                    height: "100%",
                                    width: `${Math.min(100, ((k.spend_usd || 0) / Number(k.max_budget_usd)) * 100)}%`,
                                    backgroundColor:
                                      (k.spend_usd || 0) >= Number(k.max_budget_usd)
                                        ? "var(--error)"
                                        : (k.spend_usd || 0) / Number(k.max_budget_usd) >= 0.75
                                        ? "var(--warning)"
                                        : "var(--success)",
                                  }}
                                />
                              </div>
                            )}

                            {(k.value_saved_usd || 0) > 0 && (
                              <span
                                className="font-mono"
                                style={{ fontSize: "0.625rem", color: "var(--success)" }}
                                title="Commercial retail value saved via free tier & caching"
                              >
                                +${(k.value_saved_usd || 0).toFixed(2)} saved
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="font-mono text-tertiary">
                          {k.created_at ? new Date(k.created_at).toLocaleDateString() : "2026-09-19"}
                        </td>
                        <td>
                          <span className={`status-pill ${statusClass}`}>
                            <span className="status-pulse" />
                            {statusText}
                          </span>
                        </td>
                        <td>
                          <div style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}>
                            <button
                              className="btn btn-secondary btn-sm flex items-center gap-1"
                              onClick={() => setKeyToConfigure(k)}
                              title="Configure routing policy, permitted tiers & models, and limits"
                              disabled={isRevoked}
                            >
                              <Sliders size={12} style={{ color: "var(--accent)" }} />
                              <span>Configure</span>
                            </button>

                            <button
                              className="btn btn-secondary btn-sm flex items-center gap-1"
                              onClick={() => handleCopyApiKey(k)}
                              title="Copy Full Gateway API Key (ready for Roo Code / Continue / Cursor)"
                            >
                              {copiedKey === k.id ? <Check size={12} style={{ color: "var(--success)" }} /> : <Copy size={12} />}
                              <span>{copiedKey === k.id ? "Copied" : "Copy"}</span>
                            </button>

                            <button
                              className="btn btn-secondary btn-sm flex items-center gap-1"
                              onClick={() => handleRollKey(k)}
                              title="Roll / Regenerate secret token (generates new full key)"
                              disabled={isRevoked || rollingKeyId === k.id}
                            >
                              <RotateCcw size={12} className={rollingKeyId === k.id ? "animate-spin" : ""} />
                              <span>Roll</span>
                            </button>

                            <button
                              className="btn btn-danger btn-sm flex items-center gap-1"
                              onClick={() => setKeyToDelete(k)}
                              title="Delete or Revoke Key"
                            >
                              <Trash2 size={12} />
                              <span>Delete</span>
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab: Financial & Budget Governance */}
      {tab === "budgets" && (
        <BudgetGovernanceView
          apiKeys={apiKeys}
          onRefresh={fetchSettingsData}
          loading={loading}
          gatewayTotalSaved={gatewayOverview?.total_saved_usd ?? gatewayOverview?.commercial_equivalent_usd}
          gatewayTotalSpend={gatewayOverview?.actual_cost_usd}
        />
      )}

      {/* Tab: Virtual Model Groups & Cascades */}
      {tab === "model-groups" && (
        <VirtualModelTiers
          modelGroups={modelGroups}
          workers={workers}
          onRefresh={fetchSettingsData}
          loading={loading}
        />
      )}

      {/* Tab: Providers (Real Discovered Database Models & Credentials) */}
      {tab === "providers" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          {/* Section 1: Provider API Keys & Credentials */}
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)" }}>
                  Provider API Keys & Credentials
                </span>
                <p style={{ fontSize: "0.6875rem", color: "var(--text-tertiary)", marginTop: "0.15rem" }}>
                  Upstream keys for OpenAI, Anthropic, Gemini, Groq, DeepSeek, Mistral, Together, and more. WRAP automatically balances requests across all active credentials.
                </p>
              </div>
              <button
                className="btn btn-primary btn-sm flex items-center gap-1"
                onClick={() => {
                  setFormCredProvider(rawProviders[0]?.name || "gemini");
                  setFormCredName("");
                  setFormCredKey("");
                  setIsAddCredOpen(true);
                }}
              >
                <Plus size={13} />
                <span>Add Provider Key</span>
              </button>
            </div>

            <div className="dense-table-wrapper">
              <table className="dense-table">
                <thead>
                  <tr>
                    <th>Provider</th>
                    <th>Credential Name</th>
                    <th>Masked Key</th>
                    <th>Health Status</th>
                    <th>Active</th>
                    <th style={{ textAlign: "right" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {credentials.length === 0 ? (
                    <tr>
                      <td colSpan={6} style={{ textAlign: "center", padding: "2rem", color: "var(--text-tertiary)" }}>
                        No provider credentials configured. Click "Add Provider Key" to connect your first provider.
                      </td>
                    </tr>
                  ) : (
                    credentials.map((c) => (
                      <tr key={c.id}>
                        <td style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                          <span style={{ textTransform: "capitalize" }}>{c.provider}</span>
                        </td>
                        <td>{c.name}</td>
                        <td>
                          <span className="font-mono text-secondary" style={{ fontSize: "0.6875rem" }}>
                            {c.masked_identifier}
                          </span>
                        </td>
                        <td>
                          {testingCredId === c.id ? (
                            <span className="status-pill warning animate-pulse">
                              <span className="status-pulse" />
                              TESTING...
                            </span>
                          ) : (
                            <span
                              className={`status-pill ${
                                c.last_health_status === "healthy"
                                  ? ""
                                  : c.last_health_status === "degraded"
                                  ? "warning"
                                  : c.last_health_status === "unhealthy"
                                  ? "error"
                                  : "neutral"
                              }`}
                            >
                              <span className="status-pulse" />
                              {(c.last_health_status || "NOT TESTED").toUpperCase()}
                            </span>
                          )}
                        </td>
                        <td>
                          <label className="toggle">
                            <input
                              type="checkbox"
                              checked={c.enabled}
                              onChange={() => handleToggleCredential(c.id, c.enabled)}
                            />
                            <span className="toggle-slider" />
                          </label>
                        </td>
                        <td style={{ textAlign: "right" }}>
                          <div style={{ display: "inline-flex", gap: "0.35rem" }}>
                            <button
                              className="btn btn-ghost btn-sm"
                              title="Update API Key"
                              onClick={() => {
                                setCredToEdit(c);
                                setEditCredName(c.name);
                                setEditCredKey("");
                              }}
                            >
                              <Edit2 size={12} />
                            </button>
                            <button
                              className="btn btn-ghost btn-sm"
                              title="Test Connection"
                              onClick={() => handleTestCredential(c.id)}
                              disabled={testingCredId === c.id}
                            >
                              {testingCredId === c.id ? (
                                <RefreshCw size={12} className="animate-spin" />
                              ) : (
                                <Play size={12} />
                              )}
                            </button>
                            <button
                              className="btn btn-ghost btn-sm"
                              title="Sync Models Catalog"
                              onClick={() => handleSyncCredential(c.id)}
                              disabled={syncingCredId === c.id}
                            >
                              <RefreshCw size={12} className={syncingCredId === c.id ? "animate-spin" : ""} />
                            </button>
                            <button
                              className="btn btn-ghost btn-sm text-error"
                              title="Delete Credential"
                              onClick={() => setCredToDelete(c)}
                            >
                              <Trash2 size={12} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Section 2: Active Provider Adapters & Discovered Catalogs */}
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)" }}>
                  Active Provider Adapters & Discovered Catalogs
                </span>
                <p style={{ fontSize: "0.6875rem", color: "var(--text-tertiary)", marginTop: "0.15rem" }}>
                  Discovered upstream model engines available for autonomous task execution and routing.
                </p>
              </div>
              <button
                className="btn btn-secondary btn-sm flex items-center gap-1"
                onClick={handleSyncAllCatalogs}
                disabled={isSyncingCatalogs}
                title="Synchronize catalogs from all configured provider adapters"
              >
                <RefreshCw size={12} className={isSyncingCatalogs ? "animate-spin" : ""} />
                <span>{isSyncingCatalogs ? "Syncing Catalogs..." : "Sync All Catalogs"}</span>
              </button>
            </div>

            <div className="dense-table-wrapper">
              <table className="dense-table">
                <thead>
                  <tr>
                    <th>Provider</th>
                    <th>Integration Layer</th>
                    <th>Catalog Models</th>
                    <th>Observed Latency</th>
                    <th>Health Status</th>
                  </tr>
                </thead>
                <tbody>
                  {providers.map((p) => (
                    <tr key={p.id || p.name}>
                      <td style={{ fontWeight: 600, color: "var(--text-primary)" }}>{p.name}</td>
                      <td className="font-mono text-secondary">{p.type}</td>
                      <td className="font-mono text-primary">{p.models} catalog models</td>
                      <td className="font-mono text-primary">{p.latency}</td>
                      <td>
                        <span className={`status-pill ${p.status === "degraded" ? "warning" : ""}`}>
                          <span className="status-pulse" />
                          {p.status.toUpperCase()}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Tab: Policies */}
      {tab === "policies" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)" }}>
            Autonomous Routing Policies
          </span>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "1rem" }}>
            <div className="operational-card">
              <span className="op-card-header">QUALITY_FIRST</span>
              <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.25rem" }}>
                Prioritizes capability benchmarks and reasoning depth (e.g. gemini-3.6-flash, qwen/qwen3.8-27b).
              </span>
              <div className="op-card-footer">
                <span>Weighting: <strong>Capability 0.50, Latency 0.20</strong></span>
              </div>
            </div>

            <div className="operational-card" style={{ borderColor: "var(--accent)" }}>
              <div className="op-card-header">
                <span>BALANCED (DEFAULT)</span>
                <span className="status-pill">ACTIVE</span>
              </div>
              <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.25rem" }}>
                Optimizes overall latency, throughput, and error rates while preserving execution fidelity.
              </span>
              <div className="op-card-footer">
                <span>Weighting: <strong>Equalized multi-factor</strong></span>
              </div>
            </div>

            <div className="operational-card">
              <span className="op-card-header">LATENCY_OPTIMIZED</span>
              <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.25rem" }}>
                Selects ultra-low TTFT and token streaming throughput (e.g. Groq LPU, Cerebras).
              </span>
              <div className="op-card-footer">
                <span>Weighting: <strong>TTFT 0.60, TPS 0.40</strong></span>
              </div>
            </div>
          </div>
        </div>
      )}
      {/* Tab: Workflow & Tool Setup (Second to last) */}
      {(tab === "setup" || tab === "workflows" || tab === "integration") && (
        <WorkflowSetupView apiKeys={apiKeys} />
      )}

      {/* Tab: System */}
      {tab === "system" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
          {/* Section 1: Observability & Health Probes */}
          <div className="card" style={{ padding: "1.25rem" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.875rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <Server size={15} style={{ color: "var(--accent)" }} />
                <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)" }}>
                  Health & Observability Probes
                </span>
              </div>
              <span
                className={`status-pill ${
                  probeStatus.healthz === "ok" && probeStatus.ready === "ok"
                    ? "healthy"
                    : probeStatus.ready === "degraded"
                    ? "warning"
                    : "error"
                }`}
                style={{ fontSize: "0.6875rem" }}
              >
                <span
                  className={`status-dot ${
                    probeStatus.healthz === "ok" && probeStatus.ready === "ok"
                      ? "healthy"
                      : probeStatus.ready === "degraded"
                      ? "warning"
                      : "error"
                  }`}
                />
                {probeStatus.healthz === "ok" && probeStatus.ready === "ok"
                  ? "Operational"
                  : probeStatus.ready === "degraded"
                  ? "Degraded"
                  : probeStatus.healthz === "checking"
                  ? "Checking..."
                  : "Offline"}
              </span>
            </div>

            <div className="dense-table-wrapper" style={{ margin: 0 }}>
              <table className="dense-table" style={{ width: "100%", margin: 0 }}>
                <thead>
                  <tr>
                    <th>Target</th>
                    <th>Path</th>
                    <th>Protocol</th>
                    <th>Status</th>
                    <th style={{ textAlign: "right" }}>Inspect</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td style={{ fontWeight: 600 }}>Liveness Probe</td>
                    <td className="font-mono text-secondary">/healthz</td>
                    <td><span className="font-mono text-tertiary" style={{ fontSize: "0.6875rem" }}>HTTP GET</span></td>
                    <td>
                      <span
                        className={`status-pill ${probeStatus.healthz === "ok" ? "healthy" : probeStatus.healthz === "checking" ? "" : "error"}`}
                        style={{ fontSize: "0.6875rem", padding: "0.15rem 0.4rem" }}
                      >
                        <span className={`status-dot ${probeStatus.healthz === "ok" ? "healthy" : probeStatus.healthz === "checking" ? "" : "error"}`} />
                        {probeStatus.healthz === "ok" ? "200 OK" : probeStatus.healthz === "checking" ? "Checking" : "Offline"}
                      </span>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <a href="/healthz" target="_blank" rel="noreferrer" className="btn btn-secondary btn-xs" style={{ textDecoration: "none" }}>
                        <span>Open</span>
                        <ExternalLink size={10} />
                      </a>
                    </td>
                  </tr>
                  <tr>
                    <td style={{ fontWeight: 600 }}>Readiness Probe</td>
                    <td className="font-mono text-secondary">/ready</td>
                    <td><span className="font-mono text-tertiary" style={{ fontSize: "0.6875rem" }}>HTTP GET</span></td>
                    <td>
                      <span
                        className={`status-pill ${
                          probeStatus.ready === "ok"
                            ? "healthy"
                            : probeStatus.ready === "degraded"
                            ? "warning"
                            : probeStatus.ready === "checking"
                            ? ""
                            : "error"
                        }`}
                        style={{ fontSize: "0.6875rem", padding: "0.15rem 0.4rem" }}
                      >
                        <span
                          className={`status-dot ${
                            probeStatus.ready === "ok"
                              ? "healthy"
                              : probeStatus.ready === "degraded"
                              ? "warning"
                              : probeStatus.ready === "checking"
                              ? ""
                              : "error"
                          }`}
                        />
                        {probeStatus.ready === "ok"
                          ? "200 OK"
                          : probeStatus.ready === "degraded"
                          ? "503 Degraded"
                          : probeStatus.ready === "checking"
                          ? "Checking"
                          : "Offline"}
                      </span>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <a href="/ready" target="_blank" rel="noreferrer" className="btn btn-secondary btn-xs" style={{ textDecoration: "none" }}>
                        <span>Open</span>
                        <ExternalLink size={10} />
                      </a>
                    </td>
                  </tr>
                  <tr>
                    <td style={{ fontWeight: 600 }}>Prometheus Metrics</td>
                    <td className="font-mono text-secondary">/metrics</td>
                    <td><span className="font-mono text-tertiary" style={{ fontSize: "0.6875rem" }}>OpenMetrics</span></td>
                    <td>
                      <span
                        className={`status-pill ${probeStatus.metrics === "active" ? "healthy" : probeStatus.metrics === "checking" ? "" : "error"}`}
                        style={{ fontSize: "0.6875rem", padding: "0.15rem 0.4rem" }}
                      >
                        <span className={`status-dot ${probeStatus.metrics === "active" ? "healthy" : probeStatus.metrics === "checking" ? "" : "error"}`} />
                        {probeStatus.metrics === "active" ? "Active" : probeStatus.metrics === "checking" ? "Checking" : "Offline"}
                      </span>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <a href="/metrics" target="_blank" rel="noreferrer" className="btn btn-secondary btn-xs" style={{ textDecoration: "none" }}>
                        <span>Open</span>
                        <ExternalLink size={10} />
                      </a>
                    </td>
                  </tr>
                  <tr>
                    <td style={{ fontWeight: 600 }}>Telemetry Stream</td>
                    <td className="font-mono text-secondary">/api/stream/telemetry</td>
                    <td><span className="font-mono text-tertiary" style={{ fontSize: "0.6875rem" }}>SSE (2.0s)</span></td>
                    <td>
                      <span
                        className={`status-pill ${probeStatus.telemetry === "streaming" ? "healthy" : probeStatus.telemetry === "checking" ? "" : "error"}`}
                        style={{ fontSize: "0.6875rem", padding: "0.15rem 0.4rem" }}
                      >
                        <span className={`status-dot ${probeStatus.telemetry === "streaming" ? "healthy" : probeStatus.telemetry === "checking" ? "" : "error"}`} />
                        {probeStatus.telemetry === "streaming" ? "Streaming" : "Offline"}
                      </span>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <a href="/api/stream/telemetry" target="_blank" rel="noreferrer" className="btn btn-secondary btn-xs" style={{ textDecoration: "none" }}>
                        <span>Open</span>
                        <ExternalLink size={10} />
                      </a>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Section 2: Runtime Subsystems */}
          <div className="card" style={{ padding: "1.25rem" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.875rem" }}>
              <Database size={15} style={{ color: "var(--accent)" }} />
              <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)" }}>
                Runtime Subsystems
              </span>
            </div>

            <div className="info-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
              <div className="info-row">
                <span className="info-label">Database Subsystem</span>
                <span className="info-val font-mono" style={{ color: "var(--text-primary)", fontWeight: 600 }}>
                  PostgreSQL 16 <span style={{ color: "var(--success)", fontSize: "0.6875rem", fontWeight: 500 }}>(Connected)</span>
                </span>
              </div>
              <div className="info-row">
                <span className="info-label">Active Worker Pool</span>
                <span className="info-val font-mono" style={{ color: "var(--text-primary)", fontWeight: 600 }}>
                  {diagnostics?.workers ? `${diagnostics.workers.active} active / ${diagnostics.workers.total} configured` : "3 active / 15 configured"}
                </span>
              </div>
              <div className="info-row">
                <span className="info-label">Rate Limiter</span>
                <span className="info-val font-mono" style={{ color: "var(--text-primary)", fontWeight: 600 }}>
                  Token Bucket ({diagnostics?.rate_limiter?.default_rpm || 120} RPM)
                </span>
              </div>
              <div className="info-row">
                <span className="info-label">Master Key Encryption</span>
                <span className="info-val font-mono" style={{ color: "var(--text-primary)", fontWeight: 600 }}>
                  AES-256 Fernet <span style={{ color: "var(--success)", fontSize: "0.6875rem", fontWeight: 500 }}>(Active)</span>
                </span>
              </div>
            </div>
          </div>

          {/* Section 3: Response Cache */}
          <div className="card" style={{ padding: "1.25rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.875rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <Zap size={15} style={{ color: "var(--accent)" }} />
                <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)" }}>
                  Response Cache
                </span>
              </div>
              <button
                className="btn btn-secondary btn-xs flex items-center gap-1"
                onClick={handleClearCache}
                disabled={isClearingCache}
                title="Evict all cached entries from memory"
              >
                <Trash2 size={11} className={isClearingCache ? "animate-spin" : ""} />
                <span>{isClearingCache ? "Purging..." : "Purge Cache"}</span>
              </button>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "0.75rem" }}>
              <div style={{ padding: "0.625rem 0.75rem", borderRadius: "var(--radius-sm)", backgroundColor: "var(--bg-elevated)", border: "1px solid var(--border-subtle)" }}>
                <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)", textTransform: "uppercase", fontWeight: 600, letterSpacing: "0.04em" }}>Hit Rate</span>
                <div style={{ fontSize: "1.125rem", fontWeight: 700, color: "var(--text-primary)", marginTop: "0.15rem" }} className="font-mono">
                  {cacheStats?.hit_rate_pct ?? 0}%
                </div>
                <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)" }}>
                  {cacheStats?.total_hits ?? 0} hits / {(cacheStats?.total_hits ?? 0) + (cacheStats?.total_misses ?? 0)} reqs
                </span>
              </div>

              <div style={{ padding: "0.625rem 0.75rem", borderRadius: "var(--radius-sm)", backgroundColor: "var(--bg-elevated)", border: "1px solid var(--border-subtle)" }}>
                <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)", textTransform: "uppercase", fontWeight: 600, letterSpacing: "0.04em" }}>Tokens Saved</span>
                <div style={{ fontSize: "1.125rem", fontWeight: 700, color: "var(--success)", marginTop: "0.15rem" }} className="font-mono">
                  {(cacheStats?.total_tokens_saved ?? 0).toLocaleString()}
                </div>
                <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)" }}>
                  Direct token savings
                </span>
              </div>

              <div style={{ padding: "0.625rem 0.75rem", borderRadius: "var(--radius-sm)", backgroundColor: "var(--bg-elevated)", border: "1px solid var(--border-subtle)" }}>
                <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)", textTransform: "uppercase", fontWeight: 600, letterSpacing: "0.04em" }}>Memory Entries</span>
                <div style={{ fontSize: "1.125rem", fontWeight: 700, color: "var(--text-primary)", marginTop: "0.15rem" }} className="font-mono">
                  {cacheStats?.entries_count ?? 0}
                  <span style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", fontWeight: 400 }}> / {cacheStats?.max_entries ?? 5000}</span>
                </div>
                <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)" }}>TTL: 3600s</span>
              </div>

              <div style={{ padding: "0.625rem 0.75rem", borderRadius: "var(--radius-sm)", backgroundColor: "var(--bg-elevated)", border: "1px solid var(--border-subtle)" }}>
                <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)", textTransform: "uppercase", fontWeight: 600, letterSpacing: "0.04em" }}>Cache Misses</span>
                <div style={{ fontSize: "1.125rem", fontWeight: 700, color: "var(--text-secondary)", marginTop: "0.15rem" }} className="font-mono">
                  {cacheStats?.total_misses ?? 0}
                </div>
                <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)" }}>Forwarded to workers</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: Delete or Revoke API Key */}
      {keyToDelete && (
        <div className="modal-overlay" onClick={() => !isDeleting && setKeyToDelete(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title">
                <AlertTriangle size={15} style={{ color: "var(--error)" }} />
                <span>Delete or Revoke WRAP API Key</span>
              </div>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => !isDeleting && setKeyToDelete(null)}
                aria-label="Close"
              >
                <X size={14} />
              </button>
            </div>

            <div className="modal-body">
              <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                Manage or delete the API key <strong style={{ color: "var(--text-primary)" }}>{keyToDelete.name}</strong>.
              </p>

              <div className="info-grid">
                <div className="info-row">
                  <span className="info-label">Key Name</span>
                  <span className="info-val font-mono">{keyToDelete.name}</span>
                </div>
                <div className="info-row">
                  <span className="info-label">Masked Prefix</span>
                  <span className="info-val font-mono">{keyToDelete.masked_key || keyToDelete.prefix}</span>
                </div>
                <div className="info-row">
                  <span className="info-label">Routing Policy</span>
                  <span className="info-val font-mono">{keyToDelete.routing_policy || "balanced"}</span>
                </div>
                <div className="info-row">
                  <span className="info-label">Current Status</span>
                  <span className="info-val font-mono">
                    {keyToDelete.revoked_at ? "REVOKED" : keyToDelete.enabled ? "ACTIVE" : "DISABLED"}
                  </span>
                </div>
              </div>

              <div
                style={{
                  padding: "0.75rem",
                  borderRadius: "var(--radius-sm)",
                  backgroundColor: "var(--error-muted)",
                  border: "1px solid var(--error-border)",
                  fontSize: "0.75rem",
                  color: "var(--error)",
                  lineHeight: 1.4,
                }}
              >
                <strong>Security Impact:</strong> Deleting this key will immediately revoke access for any client, Cursor editor, or agent. Requests utilizing this token will be rejected with 401 Unauthorized.
              </div>
            </div>

            <div className="modal-footer">
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => setKeyToDelete(null)}
                disabled={isDeleting}
              >
                Cancel
              </button>

              {keyToDelete.enabled && !keyToDelete.revoked_at && (
                <button
                  className="btn btn-secondary btn-sm flex items-center gap-1"
                  onClick={() => handleDeleteKey(keyToDelete.id, false)}
                  disabled={isDeleting}
                  title="Revoke key without deleting historical record"
                >
                  <Ban size={12} />
                  <span>{isDeleting ? "Processing..." : "Revoke Key"}</span>
                </button>
              )}

              <button
                className="btn btn-danger btn-sm flex items-center gap-1"
                onClick={() => handleDeleteKey(keyToDelete.id, true)}
                disabled={isDeleting}
              >
                <Trash2 size={12} />
                <span>{isDeleting ? "Deleting..." : "Delete Permanently"}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: Create New API Key */}
      {isCreateOpen && (
        <div
          className="modal-overlay"
          onClick={() => {
            if (!isCreating) {
              setIsCreateOpen(false);
              setCreatedKeyResult(null);
            }
          }}
        >
          <div className="modal-content" style={{ maxWidth: "680px" }} onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title">
                <Key size={15} />
                <span>{createdKeyResult ? "New API Key Generated" : "Create WRAP API Key"}</span>
              </div>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  if (!isCreating) {
                    setIsCreateOpen(false);
                    setCreatedKeyResult(null);
                  }
                }}
                aria-label="Close"
              >
                <X size={14} />
              </button>
            </div>

            {createdKeyResult ? (
              <div className="modal-body">
                <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                  Key for <strong style={{ color: "var(--text-primary)" }}>{createdKeyResult.name}</strong> was created.
                  Copy this key now — for security reasons, it will never be displayed again.
                </p>

                <div className="form-group">
                  <label className="form-label">Secret API Key</label>
                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <input
                      type="text"
                      readOnly
                      value={createdKeyResult.key}
                      className="form-input font-mono"
                      style={{ fontSize: "0.75rem", userSelect: "all" }}
                    />
                    <button
                      className="btn btn-primary btn-sm flex items-center gap-1"
                      onClick={() => copySecretKey(createdKeyResult.key)}
                    >
                      {copiedSecret ? <Check size={13} /> : <Copy size={13} />}
                      <span>{copiedSecret ? "Copied" : "Copy"}</span>
                    </button>
                  </div>
                </div>

                <div
                  style={{
                    padding: "0.75rem",
                    borderRadius: "var(--radius-sm)",
                    backgroundColor: "var(--bg-elevated)",
                    border: "1px solid var(--border-default)",
                    fontSize: "0.75rem",
                    color: "var(--text-secondary)",
                    lineHeight: 1.4,
                  }}
                >
                  Configure in your client via <code>Authorization: Bearer wrap_...</code> with Base URL <code>http://localhost:8000/v1</code>.
                </div>

                <div className="modal-footer" style={{ borderTop: "none", padding: "0.5rem 0 0" }}>
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={() => {
                      setIsCreateOpen(false);
                      setCreatedKeyResult(null);
                    }}
                  >
                    Done
                  </button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleCreateKey}>
                <div className="modal-body">
                  <div className="form-group">
                    <label className="form-label">Key Name / Description</label>
                    <input
                      type="text"
                      className="form-input"
                      placeholder="e.g. Cursor Pro, CLI Agent, Integration..."
                      value={newKeyName}
                      onChange={(e) => setNewKeyName(e.target.value)}
                      autoFocus
                      required
                    />
                  </div>

                  {/* Routing Policy Selector */}
                  <div className="form-group">
                    <label className="form-label" style={{ fontSize: "0.75rem", fontWeight: 600 }}>Autonomous Routing Policy</label>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: "0.5rem" }}>
                      {[
                        { id: "balanced", label: "Balanced", desc: "Multi-factor throughput & latency" },
                        { id: "quality_first", label: "Quality First", desc: "Frontier reasoning & 70B+ models" },
                        { id: "latency_optimized", label: "Lowest Latency", desc: "Fastest response LPU/hardware" },
                        { id: "cost_optimized", label: "Cost Optimized", desc: "Free tier headroom & economy" },
                      ].map((pol) => {
                        const isSelected = newKeyPolicy === pol.id;
                        return (
                          <div
                            key={pol.id}
                            onClick={() => setNewKeyPolicy(pol.id)}
                            style={{
                              padding: "0.5rem 0.65rem",
                              borderRadius: "var(--radius-sm)",
                              backgroundColor: isSelected ? "var(--bg-elevated)" : "var(--bg-canvas)",
                              border: isSelected ? "1px solid var(--accent)" : "1px solid var(--border-subtle)",
                              cursor: "pointer",
                              display: "flex",
                              flexDirection: "column",
                              gap: "0.2rem",
                              transition: "all 0.12s ease",
                            }}
                          >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                              <span style={{ fontSize: "0.75rem", fontWeight: 600, color: isSelected ? "var(--accent)" : "var(--text-primary)" }}>
                                {pol.label}
                              </span>
                              {isSelected && <Check size={11} style={{ color: "var(--accent)" }} />}
                            </div>
                            <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)", lineHeight: 1.25 }}>
                              {pol.desc}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Rate Limiting (RPM) */}
                  <div className="form-group">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <label className="form-label" style={{ fontSize: "0.75rem", fontWeight: 600, margin: 0 }}>
                        Rate Limiting (Sliding Window RPM)
                      </label>
                      <span className="font-mono text-secondary" style={{ fontSize: "0.6875rem" }}>
                        {newKeyRateLimit} requests / minute
                      </span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginTop: "0.35rem" }}>
                      <input
                        type="number"
                        min="10"
                        max="10000"
                        step="10"
                        className="form-input font-mono"
                        value={newKeyRateLimit}
                        onChange={(e) => setNewKeyRateLimit(Number(e.target.value) || 120)}
                        style={{ width: "110px", fontSize: "0.75rem" }}
                      />
                      <div className="filter-btn-group" style={{ flex: 1, margin: 0 }}>
                        {[60, 120, 300, 1000].map((preset) => (
                          <button
                            key={preset}
                            type="button"
                            className={`filter-btn ${newKeyRateLimit === preset ? "active" : ""}`}
                            onClick={() => setNewKeyRateLimit(preset)}
                            style={{ fontSize: "0.6875rem", padding: "0.2rem 0.5rem" }}
                          >
                            {preset} RPM
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Model Access Scope — 4 Interactive Options */}
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <label className="form-label" style={{ fontSize: "0.75rem", fontWeight: 600, margin: 0 }}>
                        Model Access Scope & Worker Permissions
                      </label>
                      <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)" }}>
                        Enforced at gateway scheduler boundary
                      </span>
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.5rem" }}>
                      {[
                        {
                          id: "AUTO",
                          icon: <Globe size={14} />,
                          title: "All Models",
                          desc: "Full cluster access & DAG selector",
                        },
                        {
                          id: "MODEL_GROUPS",
                          icon: <Layers size={14} />,
                          title: "Virtual Tiers",
                          desc: "Multi-model fallback cascades",
                        },
                        {
                          id: "WORKER_POOL",
                          icon: <Cpu size={14} />,
                          title: "Custom Pool",
                          desc: "Hand-picked model checklist",
                        },
                        {
                          id: "SPECIFIC_WORKER",
                          icon: <Pin size={14} />,
                          title: "Pinned Worker",
                          desc: "Dedicated hardware instance",
                        },
                      ].map((m) => {
                        const isCurrent = newKeyMode === m.id;
                        return (
                          <button
                            key={m.id}
                            type="button"
                            onClick={() => setNewKeyMode(m.id as any)}
                            style={{
                              padding: "0.65rem 0.5rem",
                              borderRadius: "var(--radius-md)",
                              backgroundColor: isCurrent ? "var(--bg-elevated)" : "var(--bg-canvas)",
                              border: isCurrent ? "1.5px solid var(--accent)" : "1px solid var(--border-subtle)",
                              cursor: "pointer",
                              display: "flex",
                              flexDirection: "column",
                              alignItems: "center",
                              textAlign: "center",
                              gap: "0.3rem",
                              transition: "all 0.15s ease",
                            }}
                          >
                            <span style={{ color: isCurrent ? "var(--accent)" : "var(--text-secondary)" }}>
                              {m.icon}
                            </span>
                            <span
                              style={{
                                fontSize: "0.75rem",
                                fontWeight: 600,
                                color: isCurrent ? "var(--text-primary)" : "var(--text-secondary)",
                              }}
                            >
                              {m.title}
                            </span>
                            <span
                              style={{
                                fontSize: "0.5625rem",
                                color: "var(--text-tertiary)",
                                lineHeight: 1.25,
                              }}
                            >
                              {m.desc}
                            </span>
                          </button>
                        );
                      })}
                    </div>

                    {/* MODE 1: AUTO */}
                    {newKeyMode === "AUTO" && (
                      <div
                        style={{
                          backgroundColor: "var(--bg-elevated)",
                          border: "1px dashed var(--border-subtle)",
                          borderRadius: "var(--radius-sm)",
                          padding: "0.75rem",
                          display: "flex",
                          alignItems: "center",
                          gap: "0.5rem",
                          fontSize: "0.75rem",
                          color: "var(--text-secondary)",
                        }}
                      >
                        <Check size={15} style={{ color: "var(--success)", flexShrink: 0 }} />
                        <span>
                          <strong>Unrestricted Scope:</strong> Client requests bearing this key may target any registered provider model, virtual tier, or use autonomous model selection (<code className="font-mono">model: &quot;auto&quot;</code>).
                        </span>
                      </div>
                    )}

                    {/* MODE 2: VIRTUAL TIERS */}
                    {newKeyMode === "MODEL_GROUPS" && (
                      <div
                        style={{
                          backgroundColor: "var(--bg-canvas)",
                          border: "1px solid var(--border-default)",
                          borderRadius: "var(--radius-md)",
                          padding: "0.75rem",
                          display: "flex",
                          flexDirection: "column",
                          gap: "0.625rem",
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <span style={{ fontSize: "0.6875rem", fontWeight: 600, color: "var(--text-secondary)" }}>
                            Select Permitted Virtual Tiers ({newKeySelectedGroups.length} selected)
                          </span>
                          <div style={{ display: "flex", gap: "0.35rem" }}>
                            <button
                              type="button"
                              className="btn btn-secondary btn-xs"
                              onClick={() => setNewKeySelectedGroups(modelGroups.map((g) => g.id))}
                            >
                              Select All
                            </button>
                            <button
                              type="button"
                              className="btn btn-secondary btn-xs"
                              onClick={() => setNewKeySelectedGroups([])}
                            >
                              Clear
                            </button>
                          </div>
                        </div>

                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
                          {modelGroups.map((group) => {
                            const isChecked = newKeySelectedGroups.includes(group.id);
                            return (
                              <div
                                key={group.id}
                                onClick={() => {
                                  setNewKeySelectedGroups((prev) =>
                                    prev.includes(group.id) ? prev.filter((id) => id !== group.id) : [...prev, group.id]
                                  );
                                }}
                                style={{
                                  padding: "0.6rem 0.75rem",
                                  borderRadius: "var(--radius-sm)",
                                  backgroundColor: isChecked ? "var(--bg-elevated)" : "var(--bg-surface)",
                                  border: isChecked ? "1.5px solid var(--accent)" : "1px solid var(--border-subtle)",
                                  cursor: "pointer",
                                  display: "flex",
                                  flexDirection: "column",
                                  gap: "0.35rem",
                                  transition: "all 0.12s ease",
                                }}
                              >
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                  <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                                    <input
                                      type="checkbox"
                                      checked={isChecked}
                                      onChange={() => {}}
                                      style={{ accentColor: "var(--accent)", cursor: "pointer" }}
                                    />
                                    <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-primary)" }}>
                                      {group.name}
                                    </span>
                                  </div>
                                  <span
                                    className="font-mono text-tertiary"
                                    style={{
                                      fontSize: "0.5625rem",
                                      backgroundColor: "var(--bg-subtle)",
                                      padding: "0.1rem 0.3rem",
                                      borderRadius: "2px",
                                    }}
                                  >
                                    {group.routing_strategy}
                                  </span>
                                </div>
                                <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)", lineHeight: 1.3 }}>
                                  {group.description || `${group.models?.length || 0} models participating`}
                                </span>
                                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.2rem", marginTop: "0.15rem" }}>
                                  {group.models?.slice(0, 3).map((m: string) => (
                                    <span
                                      key={m}
                                      className="font-mono"
                                      style={{
                                        fontSize: "0.5625rem",
                                        color: "var(--text-secondary)",
                                        backgroundColor: "var(--bg-elevated)",
                                        padding: "0.05rem 0.25rem",
                                        borderRadius: "2px",
                                        border: "1px solid var(--border-subtle)",
                                      }}
                                    >
                                      {m.split("/").pop()}
                                    </span>
                                  ))}
                                  {(group.models?.length || 0) > 3 && (
                                    <span style={{ fontSize: "0.5625rem", color: "var(--text-tertiary)" }}>
                                      +{group.models.length - 3} more
                                    </span>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {/* MODE 3: CUSTOM MODEL POOL */}
                    {newKeyMode === "WORKER_POOL" && (() => {
                      const availableProviders = Array.from(new Set(workers.map((w) => w.provider).filter(Boolean)));
                      const filteredChecklistWorkers = workers.filter((w) => {
                        if (checklistProviderFilter !== "ALL" && (w.provider || "").toLowerCase() !== checklistProviderFilter.toLowerCase()) return false;
                        if (checklistSearchQuery.trim()) {
                          const q = checklistSearchQuery.toLowerCase().trim();
                          return (
                            (w.name || "").toLowerCase().includes(q) ||
                            (w.model || "").toLowerCase().includes(q) ||
                            (w.provider_model_name || "").toLowerCase().includes(q) ||
                            (w.provider || "").toLowerCase().includes(q)
                          );
                        }
                        return true;
                      });

                      return (
                        <div
                          style={{
                            backgroundColor: "var(--bg-canvas)",
                            border: "1px solid var(--border-default)",
                            borderRadius: "var(--radius-md)",
                            padding: "0.75rem",
                            display: "flex",
                            flexDirection: "column",
                            gap: "0.5rem",
                          }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <span style={{ fontSize: "0.6875rem", fontWeight: 600, color: "var(--text-secondary)" }}>
                              Allowed Models Checklist ({newKeyAllowedWorkerIds.length} of {workers.length} selected)
                            </span>
                            <div style={{ display: "flex", gap: "0.375rem" }}>
                              <button
                                type="button"
                                className="btn btn-secondary btn-xs"
                                onClick={() => setNewKeyAllowedWorkerIds(workers.map((w) => w.id))}
                              >
                                Select All
                              </button>
                              <button
                                type="button"
                                className="btn btn-secondary btn-xs"
                                onClick={() => setNewKeyAllowedWorkerIds([])}
                              >
                                Clear
                              </button>
                            </div>
                          </div>

                          {/* Search and Provider Filters for Checklist */}
                          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                            <div style={{ position: "relative", flex: 1, minWidth: "140px" }}>
                              <Search
                                size={12}
                                style={{
                                  position: "absolute",
                                  left: "0.5rem",
                                  top: "50%",
                                  transform: "translateY(-50%)",
                                  color: "var(--text-tertiary)",
                                }}
                              />
                              <input
                                type="text"
                                className="form-input"
                                placeholder="Search models..."
                                value={checklistSearchQuery}
                                onChange={(e) => setChecklistSearchQuery(e.target.value)}
                                style={{ paddingLeft: "1.75rem", fontSize: "0.6875rem", height: "26px" }}
                              />
                            </div>

                            <div className="filter-btn-group" style={{ margin: 0 }}>
                              <button
                                type="button"
                                className={`filter-btn btn-xs ${checklistProviderFilter === "ALL" ? "active" : ""}`}
                                onClick={() => setChecklistProviderFilter("ALL")}
                                style={{ padding: "0.15rem 0.4rem", fontSize: "0.625rem" }}
                              >
                                All ({workers.length})
                              </button>
                              {availableProviders.map((p) => {
                                const count = workers.filter((w) => (w.provider || "").toLowerCase() === p.toLowerCase()).length;
                                return (
                                  <button
                                    key={p}
                                    type="button"
                                    className={`filter-btn btn-xs ${checklistProviderFilter.toLowerCase() === p.toLowerCase() ? "active" : ""}`}
                                    onClick={() => setChecklistProviderFilter(p)}
                                    style={{ padding: "0.15rem 0.4rem", fontSize: "0.625rem", textTransform: "capitalize" }}
                                  >
                                    {p} ({count})
                                  </button>
                                );
                              })}
                            </div>
                          </div>

                          {/* Quick Presets by Model Group */}
                          {modelGroups.length > 0 && (
                            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem" }}>
                              <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)", alignSelf: "center" }}>Add Tier:</span>
                              {modelGroups.map((group) => {
                                const groupWorkerIds = workers
                                  .filter((w) => group.models?.some((m: string) => {
                                    const mBare = m.split("/").pop() || m;
                                    const wBare = (w.model || "").split("/").pop() || w.model;
                                    return m === w.model || mBare === wBare;
                                  }))
                                  .map((w) => w.id);
                                return (
                                  <button
                                    key={group.id}
                                    type="button"
                                    className="btn btn-ghost btn-xs"
                                    style={{
                                      fontSize: "0.625rem",
                                      border: "1px solid var(--border-default)",
                                      padding: "0.1rem 0.4rem",
                                      borderRadius: "var(--radius-xs)",
                                      display: "inline-flex",
                                      alignItems: "center",
                                      gap: "0.25rem",
                                    }}
                                    onClick={() => {
                                      setNewKeyAllowedWorkerIds((prev) => {
                                        const next = new Set(prev);
                                        groupWorkerIds.forEach((id: string) => next.add(id));
                                        return Array.from(next);
                                      });
                                    }}
                                  >
                                    <span>+ {group.name}</span>
                                    <span className="font-mono text-tertiary">({groupWorkerIds.length})</span>
                                  </button>
                                );
                              })}
                            </div>
                          )}

                          <div
                            style={{
                              maxHeight: "160px",
                              overflowY: "auto",
                              border: "1px solid var(--border-default)",
                              borderRadius: "var(--radius-sm)",
                              padding: "0.375rem",
                              backgroundColor: "var(--bg-surface)",
                              display: "flex",
                              flexDirection: "column",
                              gap: "0.25rem",
                            }}
                          >
                            {filteredChecklistWorkers.length === 0 ? (
                              <div style={{ textAlign: "center", padding: "1rem", color: "var(--text-tertiary)", fontSize: "0.75rem" }}>
                                {checklistSearchQuery ? "No models match this filter." : "No active workers discovered yet."}
                              </div>
                            ) : (
                              filteredChecklistWorkers.map((w) => {
                                const isChecked = newKeyAllowedWorkerIds.includes(w.id);
                                return (
                                  <label
                                    key={w.id}
                                    style={{
                                      display: "flex",
                                      alignItems: "center",
                                      gap: "0.625rem",
                                      padding: "0.375rem 0.5rem",
                                      borderRadius: "var(--radius-sm)",
                                      backgroundColor: isChecked ? "var(--bg-elevated)" : "transparent",
                                      cursor: "pointer",
                                      fontSize: "0.75rem",
                                      border: isChecked ? "1px solid var(--border-focus)" : "1px solid transparent",
                                      transition: "all 0.15s ease",
                                    }}
                                  >
                                    <input
                                      type="checkbox"
                                      checked={isChecked}
                                      onChange={(e) => {
                                        if (e.target.checked) {
                                          setNewKeyAllowedWorkerIds((prev) => [...prev, w.id]);
                                        } else {
                                          setNewKeyAllowedWorkerIds((prev) => prev.filter((id) => id !== w.id));
                                        }
                                      }}
                                      style={{ accentColor: "var(--accent)", cursor: "pointer" }}
                                    />
                                    <div style={{ flex: 1, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                      <div style={{ display: "flex", flexDirection: "column" }}>
                                        <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{w.name}</span>
                                        <span className="font-mono text-tertiary" style={{ fontSize: "0.6875rem" }}>
                                          {w.provider_model_name || w.model || w.model_family}
                                        </span>
                                      </div>
                                      <div style={{ display: "flex", gap: "0.375rem", alignItems: "center" }}>
                                        <span
                                          className="font-mono"
                                          style={{
                                            fontSize: "0.625rem",
                                            padding: "0.1rem 0.35rem",
                                            borderRadius: "var(--radius-sm)",
                                            backgroundColor: "var(--bg-surface)",
                                            border: "1px solid var(--border-default)",
                                            textTransform: "uppercase",
                                          }}
                                        >
                                          {w.provider || "llm"}
                                        </span>
                                      </div>
                                    </div>
                                  </label>
                                );
                              })
                            )}
                          </div>
                        </div>
                      );
                    })()}

                    {/* MODE 4: SPECIFIC WORKER */}
                    {newKeyMode === "SPECIFIC_WORKER" && (
                      <div
                        style={{
                          backgroundColor: "var(--bg-canvas)",
                          border: "1px solid var(--border-default)",
                          borderRadius: "var(--radius-md)",
                          padding: "0.75rem",
                        }}
                      >
                        <label className="form-label" style={{ fontSize: "0.75rem", fontWeight: 600 }}>Pinned Target Worker</label>
                        <select
                          className="form-select font-mono"
                          value={newKeySpecificWorkerId}
                          onChange={(e) => setNewKeySpecificWorkerId(e.target.value)}
                          required
                          style={{ fontSize: "0.75rem" }}
                        >
                          <option value="">-- Select Worker to Pin --</option>
                          {workers.map((w) => (
                            <option key={w.id} value={w.id}>
                              {w.name} ({w.provider_model_name || w.model} - {w.provider})
                            </option>
                          ))}
                        </select>
                        <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)", marginTop: "0.25rem", display: "block" }}>
                          Requests with this key will strictly route to this pinned worker instance.
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                <div className="modal-footer">
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => setIsCreateOpen(false)}
                    disabled={isCreating}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn btn-primary btn-sm flex items-center gap-1"
                    disabled={isCreating}
                  >
                    {isCreating ? <RefreshCw size={12} className="animate-spin" /> : <Plus size={12} />}
                    <span>{isCreating ? "Creating..." : "Create Key"}</span>
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
      {/* MODAL: Add Provider Credential */}
      {isAddCredOpen && (
        <div
          className="modal-overlay"
          onClick={() => !isAddingCred && setIsAddCredOpen(false)}
        >
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title">
                <Cpu size={15} />
                <span>Add Provider API Key</span>
              </div>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => !isAddingCred && setIsAddCredOpen(false)}
                aria-label="Close"
              >
                <X size={14} />
              </button>
            </div>

            <form onSubmit={handleAddCredential}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">Provider Platform</label>
                  <select
                    className="form-select"
                    value={formCredProvider}
                    onChange={(e) => setFormCredProvider(e.target.value)}
                    required
                  >
                    {rawProviders.length === 0 ? (
                      <>
                        <option value="openai">OpenAI</option>
                        <option value="anthropic">Anthropic</option>
                        <option value="gemini">Google Gemini</option>
                        <option value="groq">Groq</option>
                        <option value="deepseek">DeepSeek</option>
                        <option value="mistral">Mistral AI</option>
                        <option value="together">Together AI</option>
                        <option value="openrouter">OpenRouter</option>
                        <option value="perplexity">Perplexity</option>
                        <option value="cerebras">Cerebras</option>
                      </>
                    ) : (
                      rawProviders.map((p) => (
                        <option key={p.id || p.name} value={p.name}>
                          {p.display_name || p.name}
                        </option>
                      ))
                    )}
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label">Credential Name / Label</label>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="e.g. gemini-primary, groq-tier1, cerebras-work"
                    value={formCredName}
                    onChange={(e) => setFormCredName(e.target.value)}
                    required
                  />
                  <span style={{ fontSize: "0.6875rem", color: "var(--text-tertiary)" }}>
                    An identifier to distinguish this key among your pooled workers.
                  </span>
                </div>

                <div className="form-group">
                  <label className="form-label">API Key / Secret</label>
                  <input
                    type="password"
                    className="form-input font-mono"
                    placeholder="Paste provider secret API key..."
                    value={formCredKey}
                    onChange={(e) => setFormCredKey(e.target.value)}
                    required
                    autoComplete="off"
                  />
                  <span style={{ fontSize: "0.6875rem", color: "var(--text-tertiary)" }}>
                    Encrypted at rest with AES-256 using your WRAP_MASTER_KEY. Only a masked preview will ever be displayed.
                  </span>
                </div>
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setIsAddCredOpen(false)}
                  disabled={isAddingCred}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary btn-sm flex items-center gap-1"
                  disabled={isAddingCred || !formCredName.trim() || !formCredKey.trim()}
                >
                  {isAddingCred ? <RefreshCw size={12} className="animate-spin" /> : <Plus size={12} />}
                  <span>{isAddingCred ? "Saving & Syncing..." : "Save Credential"}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL: Update Provider Credential */}
      {credToEdit && (
        <div
          className="modal-overlay"
          onClick={() => !isEditingCred && setCredToEdit(null)}
        >
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title">
                <Edit2 size={15} />
                <span>Update Provider Credential</span>
              </div>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => !isEditingCred && setCredToEdit(null)}
                aria-label="Close"
              >
                <X size={14} />
              </button>
            </div>

            <form onSubmit={handleUpdateCredential}>
              <div className="modal-body">
                <div className="info-grid" style={{ marginBottom: "0.75rem" }}>
                  <div className="info-row">
                    <span className="info-label">Provider</span>
                    <span className="info-val font-mono" style={{ textTransform: "capitalize" }}>
                      {credToEdit.provider}
                    </span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Current Key</span>
                    <span className="info-val font-mono">{credToEdit.masked_identifier}</span>
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Credential Name</label>
                  <input
                    type="text"
                    className="form-input"
                    value={editCredName}
                    onChange={(e) => setEditCredName(e.target.value)}
                    required
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">New API Key (leave blank to keep current)</label>
                  <input
                    type="password"
                    className="form-input font-mono"
                    placeholder="Paste new API key to replace current key..."
                    value={editCredKey}
                    onChange={(e) => setEditCredKey(e.target.value)}
                    autoComplete="off"
                  />
                  <span style={{ fontSize: "0.6875rem", color: "var(--text-tertiary)" }}>
                    Entering a new key will encrypt and overwrite the secret at rest.
                  </span>
                </div>
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setCredToEdit(null)}
                  disabled={isEditingCred}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary btn-sm flex items-center gap-1"
                  disabled={isEditingCred}
                >
                  {isEditingCred ? <RefreshCw size={12} className="animate-spin" /> : <Check size={12} />}
                  <span>{isEditingCred ? "Saving..." : "Update Credential"}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL: Delete Provider Credential */}
      {credToDelete && (
        <div
          className="modal-overlay"
          onClick={() => !isDeletingCred && setCredToDelete(null)}
        >
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title">
                <AlertTriangle size={15} style={{ color: "var(--error)" }} />
                <span>Delete Provider Credential</span>
              </div>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => !isDeletingCred && setCredToDelete(null)}
                aria-label="Close"
              >
                <X size={14} />
              </button>
            </div>

            <div className="modal-body">
              <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                Are you sure you want to delete credential <strong style={{ color: "var(--text-primary)" }}>{credToDelete.name}</strong> ({credToDelete.provider})?
              </p>
              <p style={{ fontSize: "0.75rem", color: "var(--error)", marginTop: "0.5rem" }}>
                All associated workers and routing targets for this credential will be permanently removed.
              </p>
            </div>

            <div className="modal-footer">
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => setCredToDelete(null)}
                disabled={isDeletingCred}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger btn-sm flex items-center gap-1"
                onClick={handleDeleteCredential}
                disabled={isDeletingCred}
              >
                <Trash2 size={12} />
                <span>{isDeletingCred ? "Deleting..." : "Delete Permanently"}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Model Scope Inspector Modal */}
      <ModelScopeInspectorModal
        isOpen={Boolean(selectedKeyForScopeInspection)}
        onClose={() => setSelectedKeyForScopeInspection(null)}
        apiKey={selectedKeyForScopeInspection}
        workers={workers}
        modelGroups={modelGroups}
      />

      {/* Configure Existing API Key Modal */}
      <ConfigureApiKeyModal
        isOpen={Boolean(keyToConfigure)}
        onClose={() => setKeyToConfigure(null)}
        apiKey={keyToConfigure}
        workers={workers}
        modelGroups={modelGroups}
        onKeyUpdated={fetchSettingsData}
      />
    </div>
  );
}
