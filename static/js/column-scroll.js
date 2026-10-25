// Keep the overflow cue tied to the actual viewport, including card resizes.
export function createColumnScrollCues(root) {
  function update(body) {
    body.parentElement.classList.toggle("has-more", body.scrollHeight - body.clientHeight - body.scrollTop > 1);
  }
  const observer = new ResizeObserver((entries) => {
    const bodies = new Set(entries.map(({ target }) => target.closest(".column-cards")));
    for (const body of bodies) if (body?.isConnected) update(body);
  });
  root.addEventListener("scroll", ({ target }) => {
    if (target.matches?.(".column-cards")) update(target);
  }, { capture: true, passive: true });
  return function refresh() {
    observer.disconnect();
    for (const body of root.querySelectorAll(".column-cards")) {
      update(body);
      observer.observe(body);
      for (const card of body.children) observer.observe(card);
    }
  };
}
