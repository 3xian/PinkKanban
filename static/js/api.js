export async function api(path, options = {}) {
  const readOnly = ["GET", "HEAD", "OPTIONS"].includes((options.method || "GET").toUpperCase());
  const { timeoutMs = readOnly ? 15000 : 30000, signal, ...requestOptions } = options;
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
    throw new RangeError("timeoutMs must be a positive, finite number");
  }
  const headers = new Headers({ "X-Kanban": "1" });
  new Headers(options.headers).forEach((value, key) => headers.set(key, value));
  let body = options.body;
  if (body && !(body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(body);
  }

  if (signal?.aborted) throw signal.reason;
  const controller = new AbortController();
  const cancel = () => controller.abort(signal.reason);
  signal?.addEventListener("abort", cancel, { once: true });
  const timeoutError = new Error(readOnly
    ? "请求超时，请检查网络后重试"
    : "请求超时，操作可能已保存，请刷新确认后再重试");
  timeoutError.name = "TimeoutError";
  const timer = setTimeout(() => controller.abort(timeoutError), timeoutMs);
  let onAbort;
  // Race the entire operation, including body consumption, so even a stalled
  // response cannot leave the caller waiting indefinitely.
  const aborted = new Promise((_, reject) => {
    onAbort = () => reject(controller.signal.reason);
    if (controller.signal.aborted) onAbort();
    else controller.signal.addEventListener("abort", onAbort, { once: true });
  });
  try {
    return await Promise.race([aborted, (async () => {
      const response = await fetch(path, {
        credentials: "same-origin", ...requestOptions, headers, body, signal: controller.signal,
      });
      const data = await response.json().catch((error) => {
        if (controller.signal.aborted) throw controller.signal.reason;
        if (error instanceof SyntaxError) return {};
        throw error;
      });
      if (!response.ok) {
        const error = new Error(typeof data?.detail === "string" ? data.detail : "请求失败");
        error.status = response.status;
        throw error;
      }
      return data;
    })()]);
  } catch (error) {
    if (controller.signal.aborted) throw controller.signal.reason;
    if (error?.status) throw error;
    if (error instanceof TypeError) {
      throw new Error(readOnly
        ? "网络连接失败，请检查网络后重试"
        : "网络连接中断，操作可能已保存，请刷新确认后再重试", { cause: error });
    }
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", cancel);
    controller.signal.removeEventListener("abort", onAbort);
  }
}
