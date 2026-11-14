// API client for the approval console (S4.2 design K-a, K-h).
// Gated by HELIOS_ENABLE_CONSOLE (helios/api/__init__.py): when it is off the
// API has no /v1/queue and compose does not start the console.
//
// The console and the API share one origin (nginx proxies /v1 and /health),
// so requests are relative. The key travels only in the X-API-Key header and
// lives in sessionStorage for the browser session; it is never put in a URL.

const KEY_SLOT = "helios.apiKey";

export function keyStore(storage) {
  return {
    get: () => storage.getItem(KEY_SLOT),
    set: (key) => storage.setItem(KEY_SLOT, key),
    clear: () => storage.removeItem(KEY_SLOT),
  };
}

export class ApiError extends Error {
  constructor(status, title, detail) {
    super(title);
    this.status = status;
    this.detail = detail;
  }
}

export function makeApi(fetchFn, getKey) {
  async function call(method, path, body) {
    const headers = { Accept: "application/json" };
    const key = getKey();
    if (key) headers["X-API-Key"] = key;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const resp = await fetchFn(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
      credentials: "omit",
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new ApiError(resp.status, data.title ?? `HTTP ${resp.status}`, data.detail);
    }
    return data;
  }
  return {
    get: (path) => call("GET", path),
    post: (path, body) => call("POST", path, body),
  };
}
