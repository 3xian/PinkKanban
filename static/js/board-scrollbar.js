// A viewport-edge scrollbar that follows the board's real scroll position.
export function createBoardScrollbar(root) {
  let canvas, bar, track, thumb, frame = 0, drag = null;
  const maximum = () => Math.max(0, canvas.scrollWidth - canvas.clientWidth);
  function update() {
    frame = 0;
    if (!canvas?.isConnected) return;
    const max = maximum();
    bar.hidden = !canvas.getClientRects().length || max <= 1;
    if (bar.hidden) return;
    const rect = canvas.getBoundingClientRect();
    bar.style.left = `${rect.left}px`;
    bar.style.width = `${rect.width}px`;
    const navigation = root.querySelector(".tabbar");
    bar.style.bottom = `${navigation?.getClientRects().length ? innerHeight - navigation.getBoundingClientRect().top : 0}px`;
    const width = track.clientWidth;
    const size = Math.min(width, Math.max(44, width * canvas.clientWidth / canvas.scrollWidth));
    thumb.style.width = `${size}px`;
    thumb.style.transform = `translateX(${(width - size) * canvas.scrollLeft / max}px)`;
    thumb.setAttribute("aria-valuenow", String(Math.round(canvas.scrollLeft / max * 100)));
  }
  function schedule() {
    if (!frame) frame = requestAnimationFrame(update);
  }
  const resize = new ResizeObserver(schedule);
  root.addEventListener("scroll", (event) => {
    if (event.target === canvas) schedule();
  }, { capture: true, passive: true });
  window.addEventListener("resize", schedule, { passive: true });
  root.addEventListener("pointerdown", (event) => {
    if (!track?.contains(event.target) || event.button !== 0) return;
    event.preventDefault();
    thumb.focus({ preventScroll: true });
    const travel = track.clientWidth - thumb.offsetWidth;
    if (travel <= 0) return;
    canvas.classList.add("is-scrollbar-dragging");
    if (event.target !== thumb) {
      canvas.scrollLeft = (event.clientX - track.getBoundingClientRect().left - thumb.offsetWidth / 2) / travel * maximum();
    }
    drag = { x: event.clientX, left: canvas.scrollLeft, ratio: maximum() / travel };
    thumb.setPointerCapture(event.pointerId);
    update();
  });
  root.addEventListener("pointermove", (event) => {
    if (!drag) return;
    canvas.scrollLeft = drag.left + (event.clientX - drag.x) * drag.ratio;
    update();
  });
  function stop() {
    drag = null;
    canvas?.classList.remove("is-scrollbar-dragging");
  }
  root.addEventListener("pointerup", stop);
  root.addEventListener("pointercancel", stop);
  root.addEventListener("lostpointercapture", stop);
  root.addEventListener("focusout", (event) => {
    if (event.target === thumb) stop();
  });
  root.addEventListener("keydown", (event) => {
    if (event.target !== thumb) return;
    const positions = {
      ArrowLeft: canvas.scrollLeft - 80, ArrowRight: canvas.scrollLeft + 80,
      PageUp: canvas.scrollLeft - canvas.clientWidth, PageDown: canvas.scrollLeft + canvas.clientWidth,
      Home: 0, End: maximum(),
    };
    if (!(event.key in positions)) return;
    event.preventDefault();
    canvas.classList.add("is-scrollbar-dragging");
    canvas.scrollLeft = positions[event.key];
    update();
  });
  return function refresh() {
    stop();
    resize.disconnect();
    canvas = root.querySelector(".board-canvas");
    bar = root.querySelector(".board-scrollbar");
    if (!canvas || !bar) return;
    track = bar.querySelector(".board-scrollbar-track");
    thumb = bar.querySelector(".board-scrollbar-thumb");
    resize.observe(canvas);
    const navigation = root.querySelector(".tabbar");
    if (navigation) resize.observe(navigation);
    for (const column of canvas.children) resize.observe(column);
    update();
  };
}
