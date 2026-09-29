export function installDrag({ canDrag, onTap, onDrop, onDragChange }) {
  let session = null;
  let timer = null;
  let listening = null;

  function stopTimer() {
    clearTimeout(timer);
    timer = null;
  }

  function cleanupGhost() {
    session?.ghost?.remove();
    session?.placeholder?.remove();
    session?.origin?.classList.remove("is-dragging");
    if (session?.origin) session.origin.hidden = false;
    document.querySelector(".board-canvas")?.classList.remove("is-sorting");
    if (session?.frame) cancelAnimationFrame(session.frame);
  }

  function cardDrop(current) {
    const column = current.placeholder?.closest("[data-drop-column]");
    return {
      kind: "card",
      id: current.id,
      columnId: column ? Number(column.dataset.dropColumn) : null,
      index: column ? indexBefore(column.querySelector(".column-cards"), current) : 0,
    };
  }

  function columnDrop(current) {
    const board = document.querySelector(".board-canvas");
    let index = 0;
    if (board && current.placeholder) {
      for (const child of board.children) {
        if (child === current.placeholder) break;
        if (child.matches("[data-drop-column]") && child !== current.origin) index += 1;
      }
    }
    return { kind: "column", id: current.id, columnId: null, index };
  }

  function indexBefore(body, current) {
    if (!body || !current.placeholder) return 0;
    let index = 0;
    for (const child of body.children) {
      if (child === current.placeholder) return index;
      if (child === current.origin || child.classList.contains("drag-ghost")) continue;
      if (child.matches("[data-drag='card']")) index += 1;
    }
    return index;
  }

  function end(event, dropped) {
    const current = session;
    stopTimer();
    detach();
    if (!current) return;
    const detail = dropped && current.ready ? (current.kind === "column" ? columnDrop(current) : cardDrop(current)) : null;
    cleanupGhost();
    session = null;
    onDragChange?.(false);
    if (detail) onDrop?.(detail);
    else if (!current.ready && !current.scrolled) onTap?.(current.kind, current.id);
    if (event) event.preventDefault();
  }

  function movePlaceholder(x, y) {
    session.ghost.style.display = "none";
    const hit = document.elementFromPoint(x, y);
    session.ghost.style.display = "";
    if (session.kind === "card") {
      const column = hit?.closest("[data-drop-column]");
      const body = column?.querySelector(".column-cards");
      if (!body) return;
      const card = hit?.closest("[data-drag='card']");
      if (card && card !== session.origin && body.contains(card)) {
        const rect = card.getBoundingClientRect();
        body.insertBefore(session.placeholder, y < rect.top + rect.height / 2 ? card : card.nextSibling);
      } else if (!body.contains(session.placeholder)) body.append(session.placeholder);
      return;
    }
    const board = document.querySelector(".board-canvas");
    const column = hit?.closest("[data-drop-column]");
    if (!board || !column || column === session.origin) return;
    const rect = column.getBoundingClientRect();
    board.insertBefore(session.placeholder, x < rect.left + rect.width / 2 ? column : column.nextSibling);
  }

  function tick() {
    if (!session?.ready) return;
    const board = document.querySelector(".board-canvas");
    if (board) {
      const rect = board.getBoundingClientRect();
      if (session.x < rect.left + 56) board.scrollLeft -= 16;
      if (session.x > rect.right - 56) board.scrollLeft += 16;
    }
    session.frame = requestAnimationFrame(tick);
  }

  function follow(event) {
    if (!session?.ready) return;
    session.x = event.clientX;
    session.y = event.clientY;
    session.ghost.style.left = `${event.clientX - session.dx}px`;
    session.ghost.style.top = `${event.clientY - session.dy}px`;
    movePlaceholder(event.clientX, event.clientY);
  }

  function begin(start, event) {
    if (session?.ready) return;
    const origin = start.handle;
    const rect = origin.getBoundingClientRect();
    const ghost = origin.cloneNode(true);
    ghost.classList.add("drag-ghost");
    ghost.style.width = `${rect.width}px`;
    document.body.append(ghost);
    const placeholder = document.createElement("div");
    placeholder.className = start.kind === "column" ? "column-placeholder" : "card-placeholder";
    placeholder.style.height = `${rect.height}px`;
    if (start.kind === "column") placeholder.style.width = `${rect.width}px`;
    origin.classList.add("is-dragging");
    origin.hidden = true;
    origin.after(placeholder);
    document.querySelector(".board-canvas")?.classList.add("is-sorting");
    session = {
      ...start,
      ready: true,
      origin,
      ghost,
      placeholder,
      dx: event.clientX - rect.left,
      dy: event.clientY - rect.top,
      x: event.clientX,
      y: event.clientY,
    };
    onDragChange?.(true);
    navigator.vibrate?.(12);
    follow(event);
    tick();
  }

  function detach() {
    if (!listening) return;
    window.removeEventListener("pointermove", listening.move);
    window.removeEventListener("pointerup", listening.up);
    window.removeEventListener("pointercancel", listening.up);
    listening = null;
  }

  document.addEventListener("pointerdown", (event) => {
    if (event.button != null && event.button !== 0) return;
    const handle = event.target.closest("[data-drag]");
    if (!handle) return;
    const blocked = event.target.closest("button, a, input, textarea, select, label");
    if (blocked && blocked !== handle) return;
    const kind = handle.dataset.drag;
    const id = Number(handle.dataset.id);
    if (!canDrag?.(kind, id)) return;
    const start = { x: event.clientX, y: event.clientY, kind, id, handle, pointerId: event.pointerId, scrolled: false };
    const mouse = event.pointerType === "mouse";
    const move = (ev) => {
      if (ev.pointerId !== start.pointerId) return;
      const dist = Math.hypot(ev.clientX - start.x, ev.clientY - start.y);
      if (!session?.ready && dist > 8) {
        if (mouse) begin(start, ev);
        else start.scrolled = true;
        stopTimer();
      } else follow(ev);
    };
    const up = (ev) => {
      if (ev.pointerId !== start.pointerId) return;
      const dropped = Boolean(session?.ready);
      if (!session) session = start;
      else session.scrolled = start.scrolled;
      end(ev, dropped);
    };
    listening = { move, up };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
    if (!mouse) timer = setTimeout(() => begin(start, { clientX: start.x, clientY: start.y }), 280);
  });

  document.addEventListener("touchmove", (event) => {
    if (session?.ready) event.preventDefault();
  }, { passive: false });
}
