export async function api(path, options = {}) {
  const headers = { "X-Kanban": "1", ...(options.headers || {}) };
  let body = options.body;
  if (body && !(body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(body);
  }
  const response = await fetch(path, { credentials: "same-origin", ...options, headers, body });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(typeof data.detail === "string" ? data.detail : "请求失败");
    error.status = response.status;
    throw error;
  }
  return data;
}
