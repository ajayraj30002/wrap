class ApiError extends Error {
  status: number;
  data: any;

  constructor(status: number, data: any) {
    super(data?.detail || data?.message || "An API error occurred");
    this.status = status;
    this.data = data;
  }
}

interface CacheEntry {
  data: any;
  timestamp: number;
}

const cache = new Map<string, CacheEntry>();
const inFlightPromises = new Map<string, Promise<any>>();

function getDefaultTtlMs(endpoint: string): number {
  if (endpoint.includes("/provider-models")) return 60_000;
  if (endpoint.includes("/providers") || endpoint.includes("/credentials") || endpoint.includes("/model-groups")) {
    return 15_000;
  }
  if (endpoint.includes("/dashboard/") || endpoint.includes("/workers") || endpoint.includes("/apikeys")) {
    return 5_000;
  }
  return 3_000;
}

export interface GetOptions extends RequestInit {
  cacheTtlMs?: number;
  bypassCache?: boolean;
}

async function request(endpoint: string, options: RequestInit = {}): Promise<any> {
  const headers = {
    "Content-Type": "application/json",
    ...options.headers,
  };

  let response;
  try {
    response = await fetch(endpoint, {
      ...options,
      headers,
      credentials: "include",
    });
  } catch {
    throw new ApiError(0, { detail: "Network error: Could not connect to backend" });
  }

  if (!response.ok) {
    let errorData;
    try {
      errorData = await response.json();
    } catch {
      errorData = { detail: response.statusText };
    }

    if (response.status === 401) {
      window.dispatchEvent(new Event("unauthorized"));
    }

    throw new ApiError(response.status, errorData);
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

export const apiClient = {
  get: async (endpoint: string, options?: GetOptions): Promise<any> => {
    const { cacheTtlMs, bypassCache, ...fetchOptions } = options || {};
    const ttl = cacheTtlMs !== undefined ? cacheTtlMs : getDefaultTtlMs(endpoint);
    const now = Date.now();

    // 1. Return valid cache hit if not bypassed
    if (!bypassCache && ttl > 0) {
      const cached = cache.get(endpoint);
      if (cached && now - cached.timestamp < ttl) {
        return cached.data;
      }
    }

    // 2. Deduplicate simultaneous in-flight identical GET requests
    if (inFlightPromises.has(endpoint)) {
      return inFlightPromises.get(endpoint);
    }

    const fetchPromise = request(endpoint, { ...fetchOptions, method: "GET" })
      .then((data) => {
        if (ttl > 0 && data !== null && data !== undefined) {
          cache.set(endpoint, { data, timestamp: Date.now() });
        }
        return data;
      })
      .finally(() => {
        inFlightPromises.delete(endpoint);
      });

    inFlightPromises.set(endpoint, fetchPromise);
    return fetchPromise;
  },

  getCached: (endpoint: string): any | null => {
    const entry = cache.get(endpoint);
    return entry ? entry.data : null;
  },

  invalidate: (endpointPattern?: string) => {
    if (!endpointPattern) {
      cache.clear();
      return;
    }
    for (const key of Array.from(cache.keys())) {
      if (key.includes(endpointPattern)) {
        cache.delete(key);
      }
    }
  },

  post: async (endpoint: string, data?: any, options?: RequestInit): Promise<any> => {
    const res = await request(endpoint, {
      ...options,
      method: "POST",
      body: data ? JSON.stringify(data) : undefined,
    });
    apiClient.invalidate();
    return res;
  },

  patch: async (endpoint: string, data?: any, options?: RequestInit): Promise<any> => {
    const res = await request(endpoint, {
      ...options,
      method: "PATCH",
      body: data ? JSON.stringify(data) : undefined,
    });
    apiClient.invalidate();
    return res;
  },

  delete: async (endpoint: string, options?: RequestInit): Promise<any> => {
    const res = await request(endpoint, { ...options, method: "DELETE" });
    apiClient.invalidate();
    return res;
  },
};
