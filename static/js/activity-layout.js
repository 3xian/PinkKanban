// Keep the fixed overlay aligned with the tallest task column as content changes.
export function createActivityLayout(root) {
  let frame = 0;
  function update() {
    frame = 0;
    const panel = root.querySelector(".project-activity");
    const canvas = root.querySelector(".board-canvas");
    if (!panel || !canvas) return;
    const atEnd = canvas.scrollLeft > 0 && canvas.scrollWidth - canvas.clientWidth - canvas.scrollLeft <= 1;
    // Trailing scroll space lets the last column clear the floating panel.
    const panelRect = panel.getBoundingClientRect();
    const edge = parseFloat(getComputedStyle(canvas).paddingRight);
    const reserve = canvas.getBoundingClientRect().right - panelRect.left - edge;
    canvas.style.setProperty("--activity-reserve", `${panel.open ? Math.max(0, reserve) : 0}px`);
    canvas.classList.toggle("has-activity-space", panel.open);
    if (atEnd) canvas.scrollLeft = canvas.scrollWidth;
    const columns = Array.from(root.querySelectorAll(".board-canvas > .column"));
    if (!columns.length) return;
    const rects = columns.map((column) => column.getBoundingClientRect());
    const bottomLimit = innerHeight - (matchMedia("(max-width: 900px)").matches ? 88 : 24);
    const top = Math.min(bottomLimit - 56, Math.max(8, Math.min(...rects.map((rect) => rect.top))));
    const bottom = Math.min(bottomLimit, Math.max(...rects.map((rect) => rect.bottom)));
    panel.style.setProperty("--activity-top", `${top}px`);
    panel.style.setProperty("--activity-height", `${Math.max(56, bottom - top)}px`);
  }
  function schedule() {
    if (!frame) frame = requestAnimationFrame(update);
  }
  const observer = new ResizeObserver(schedule);
  window.addEventListener("resize", schedule, { passive: true });
  root.addEventListener("scroll", schedule, { capture: true, passive: true });
  root.addEventListener("toggle", (event) => {
    if (event.target.matches?.(".project-activity")) schedule();
  }, true);
  return function refresh() {
    observer.disconnect();
    const canvas = root.querySelector(".board-canvas");
    if (canvas) observer.observe(canvas);
    const panel = root.querySelector(".project-activity");
    if (panel) observer.observe(panel);
    for (const column of root.querySelectorAll(".board-canvas > .column")) observer.observe(column);
    update();
  };
}
