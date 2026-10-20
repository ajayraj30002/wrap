export interface ProviderBadgeStyle {
  name: string;
  color: string;
  bg: string;
  border: string;
  dot: string;
}

export function getProviderBadgeStyle(provider?: string, model?: string): ProviderBadgeStyle {
  const p = (provider || "").toLowerCase().trim();
  const m = (model || "").toLowerCase().trim();

  // 0. Multi-Provider / Hybrid (DAG cross-provider execution)
  if (p.includes(",")) {
    const provs = Array.from(new Set(p.split(",").map((x) => x.trim()).filter(Boolean)));
    if (provs.length > 1) {
      return {
        name: `${provs.length} Providers`,
        color: "#a78bfa",
        bg: "rgba(167, 139, 250, 0.1)",
        border: "rgba(167, 139, 250, 0.3)",
        dot: "#a78bfa",
      };
    }
    if (provs.length === 1) {
      return getProviderBadgeStyle(provs[0], model);
    }
  }

  // 1. Google Gemini
  if (p.includes("gemini") || p.includes("google") || m.includes("gemini") || m.includes("gemma")) {
    return {
      name: "Gemini",
      color: "#818cf8",
      bg: "rgba(99, 102, 241, 0.08)",
      border: "rgba(99, 102, 241, 0.25)",
      dot: "#818cf8",
    };
  }

  // 2. Groq
  if (p.includes("groq") || m.includes("groq") || m.includes("llama") || m.includes("mixtral") || m.includes("qwen") || m.includes("allam")) {
    return {
      name: "Groq",
      color: "#fb923c",
      bg: "rgba(249, 115, 22, 0.08)",
      border: "rgba(249, 115, 22, 0.25)",
      dot: "#fb923c",
    };
  }

  // 3. Cerebras
  if (p.includes("cerebras") || m.includes("cerebras") || m.includes("wse")) {
    return {
      name: "Cerebras",
      color: "#38bdf8",
      bg: "rgba(56, 189, 248, 0.08)",
      border: "rgba(56, 189, 248, 0.25)",
      dot: "#38bdf8",
    };
  }

  // 4. Anthropic
  if (p.includes("anthropic") || p.includes("claude") || m.includes("claude") || m.includes("sonnet") || m.includes("haiku") || m.includes("opus")) {
    return {
      name: "Anthropic",
      color: "#f59e0b",
      bg: "rgba(245, 158, 11, 0.08)",
      border: "rgba(245, 158, 11, 0.25)",
      dot: "#f59e0b",
    };
  }

  // 5. OpenAI
  if (p.includes("openai") || (m.includes("gpt") && !m.includes("oss")) || m.includes("o1") || m.includes("o3")) {
    return {
      name: "OpenAI",
      color: "#34d399",
      bg: "rgba(52, 211, 153, 0.08)",
      border: "rgba(52, 211, 153, 0.25)",
      dot: "#34d399",
    };
  }

  // 6. SambaNova
  if (p.includes("sambanova") || m.includes("sambanova")) {
    return {
      name: "SambaNova",
      color: "#a855f7",
      bg: "rgba(168, 85, 247, 0.08)",
      border: "rgba(168, 85, 247, 0.25)",
      dot: "#a855f7",
    };
  }

  const formatted = p && p !== "default" ? p.charAt(0).toUpperCase() + p.slice(1) : "Groq";
  return {
    name: formatted,
    color: "var(--text-secondary)",
    bg: "var(--bg-elevated)",
    border: "var(--border-subtle)",
    dot: "var(--text-tertiary)",
  };
}

/**
 * Compact formatting for long request IDs (e.g. wrap_1ade0d3cff604b70b70749 -> wrap_1ade0d3c…)
 * Preserves namespace prefix and first 8 hex characters while saving ~120px in table layouts.
 */
export function formatShortRequestId(id: string): string {
  if (!id) return "";
  if (id.startsWith("wrap_")) {
    return `wrap_${id.slice(5, 13)}…`;
  }
  return id.length > 14 ? `${id.slice(0, 10)}…` : id;
}

export interface ExecutedModelBadgeInfo {
  isMulti: boolean;
  label: string;
  count: number;
  models: string[];
  fullTitle: string;
}

/**
 * Formats executed models cleanly for high-density tables.
 * When a DAG request executes across multiple models, formats as "DAG (N models)"
 * with full model list on tooltip, preventing horizontal table blowout.
 */
export function formatExecutedModelBadge(executedModel?: string, executionMode?: string): ExecutedModelBadgeInfo {
  const raw = (executedModel || "").trim();
  if (!raw) {
    return { isMulti: false, label: "—", count: 0, models: [], fullTitle: "—" };
  }

  const models = Array.from(new Set(raw.split(",").map((m) => m.trim()).filter(Boolean)));
  if (models.length > 1 || (executionMode === "DAG" && models.length > 1)) {
    return {
      isMulti: true,
      label: `DAG (${models.length} models)`,
      count: models.length,
      models,
      fullTitle: `DAG Multi-Worker Execution across ${models.length} models:\n• ${models.join("\n• ")}`,
    };
  }

  return {
    isMulti: false,
    label: raw,
    count: 1,
    models: [raw],
    fullTitle: raw,
  };
}

export interface SingleProviderItem {
  name: string;
  dot: string;
  color: string;
  bg: string;
  border: string;
}

export interface MultiProviderInfo {
  isMulti: boolean;
  count: number;
  providers: SingleProviderItem[];
  label: string;
  tooltip: string;
  badgeStyle: ProviderBadgeStyle;
}

/**
 * Parses single or multi-provider payloads into a structured metadata object.
 * When more than two providers participate, condenses into a neat dot cluster with
 * a concise count label (e.g. "3 Providers"), preventing table cell blowout and horizontal scroll.
 */
export function parseProviderInfo(provider?: string, model?: string): MultiProviderInfo {
  const p = (provider || "").toLowerCase().trim();
  const rawList = p.includes(",") ? p.split(",") : [p];
  const distinct = Array.from(new Set(rawList.map((x) => x.trim()).filter(Boolean)));

  if (distinct.length === 0) {
    const singleStyle = getProviderBadgeStyle(provider, model);
    return {
      isMulti: false,
      count: 1,
      providers: [
        {
          name: singleStyle.name,
          dot: singleStyle.dot,
          color: singleStyle.color,
          bg: singleStyle.bg,
          border: singleStyle.border,
        },
      ],
      label: singleStyle.name,
      tooltip: `Routed to ${singleStyle.name}`,
      badgeStyle: singleStyle,
    };
  }

  const provItems: SingleProviderItem[] = distinct.map((item) => {
    const style = getProviderBadgeStyle(item);
    return {
      name: style.name,
      dot: style.dot,
      color: style.color,
      bg: style.bg,
      border: style.border,
    };
  });

  if (provItems.length === 1) {
    const singleStyle = getProviderBadgeStyle(distinct[0], model);
    return {
      isMulti: false,
      count: 1,
      providers: [
        {
          name: singleStyle.name,
          dot: singleStyle.dot,
          color: singleStyle.color,
          bg: singleStyle.bg,
          border: singleStyle.border,
        },
      ],
      label: singleStyle.name,
      tooltip: `Routed to ${singleStyle.name}`,
      badgeStyle: singleStyle,
    };
  }

  // Multi-provider execution (2 or more)
  const label = `${provItems.length} Providers`;

  const tooltip = `Cross-Provider Distributed Execution (${provItems.length} providers):\n• ${provItems
    .map((pr) => pr.name)
    .join("\n• ")}\n(Click row for subtask breakdown)`;

  return {
    isMulti: true,
    count: provItems.length,
    providers: provItems,
    label,
    tooltip,
    badgeStyle: {
      name: label,
      color: "#a78bfa",
      bg: "rgba(167, 139, 250, 0.1)",
      border: "rgba(167, 139, 250, 0.3)",
      dot: "#a78bfa",
    },
  };
}
