// SSE invalidations are coalesced; snapshots wait until the user is idle.
export function createBoardSync({ load, apply, isBusy, onUnauthorized, onUnavailable }) {
  let projectId = null;
  let source = null;
  let timer = 0;
  let fallback = 0;
  let revision = 0;
  let request = null;
  let dirty = false;
  let pending = null;
  let paused = false;

  function schedule(delay = 120) {
    clearTimeout(timer);
    if (projectId && !paused) timer = setTimeout(flush, delay);
  }

  function refresh() {
    if (!projectId) return;
    dirty = true;
    pending = null;
    schedule();
  }

  async function flush() {
    if (!projectId || paused) return;
    if (isBusy()) { schedule(250); return; }
    if (pending && !dirty) {
      const board = pending;
      pending = null;
      apply(board);
    }
    if (!dirty || request) return;
    dirty = false;
    const current = { revision, controller: new AbortController() };
    request = current;
    let delay = 120;
    try {
      const board = await load(projectId, current.controller.signal);
      if (current !== request || current.revision !== revision) return;
      if (!dirty) pending = board;
    } catch (error) {
      if (current !== request || current.revision !== revision) return;
      if (error.status === 401) { stop(); onUnauthorized(); }
      else if (error.status === 403 || error.status === 404) { stop(); onUnavailable(); }
      else { dirty = true; delay = 3000; }
    } finally {
      if (request === current) {
        request = null;
        if (dirty || pending) schedule(delay);
      }
    }
  }

  function disconnect() {
    source?.close();
    source = null;
    clearInterval(fallback);
    fallback = 0;
  }

  function startFallback() {
    if (!fallback) {
      fallback = setInterval(refresh, 15000);
      refresh();
    }
  }

  function connect() {
    source?.close();
    source = null;
    if (typeof EventSource === "undefined") { startFallback(); return; }
    const connection = new EventSource(`/api/projects/${projectId}/events`);
    source = connection;
    connection.addEventListener("ready", () => {
      if (source !== connection) return;
      clearInterval(fallback);
      fallback = 0;
      refresh();
    });
    connection.addEventListener("change", () => { if (source === connection) refresh(); });
    connection.addEventListener("unavailable", () => {
      if (source === connection) { stop(); onUnavailable(); }
    });
    connection.addEventListener("error", () => {
      if (source !== connection) return;
      startFallback();
      // EventSource reconnects itself, except when the browser reports CLOSED.
      if (connection.readyState === EventSource.CLOSED) {
        source.close();
        source = null;
        scheduleReconnect();
      }
    });
  }

  let reconnect = 0;
  function scheduleReconnect() {
    clearTimeout(reconnect);
    reconnect = setTimeout(() => { if (projectId && !paused) connect(); }, 3000);
  }

  function stop() {
    disconnect();
    clearTimeout(timer);
    clearTimeout(reconnect);
    projectId = null;
    revision += 1;
    request?.controller.abort();
    request = pending = null;
    dirty = false;
  }

  return {
    start(id) { stop(); projectId = id; paused = document.hidden; if (!paused) connect(); },
    stop,
    invalidate() {
      revision += 1;
      request?.controller.abort();
      request = pending = null;
      refresh();
    },
    resume() { if (dirty || pending) schedule(250); },
    visibilityChanged() {
      paused = document.hidden;
      if (!projectId) return;
      revision += 1;
      request?.controller.abort();
      pending = request = null;
      clearTimeout(timer);
      clearTimeout(reconnect);
      if (paused) disconnect();
      else connect();
    },
  };
}
