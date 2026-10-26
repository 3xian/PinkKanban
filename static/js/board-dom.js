// Reconcile the board without replacing surviving cards, lists or controls.
const ITEMS = '[data-drop-column], [data-drag="card"]';

function key(node) {
  if (node.nodeType !== 1) return null;
  if (node.id) return `id:${node.id}`;
  if (node.hasAttribute("data-drop-column")) return `column:${node.dataset.dropColumn}`;
  if (node.dataset.drag === "card") return `card:${node.dataset.id}`;
  if (node.dataset.form) return `form:${node.dataset.form}`;
  if (node.dataset.act) return `action:${JSON.stringify([node.dataset.act, node.dataset.id, node.dataset.column, node.dataset.key, node.dataset.filter, node.dataset.value])}`;
  return null;
}

function shape(node) {
  return `${node.nodeName}:${node.nodeType === 1 ? node.getAttribute("class")?.split(" ")[0] || "" : ""}`;
}

function patch(node, next, items) {
  if (node.isEqualNode(next)) return;
  if (node.nodeType !== 1) {
    node.nodeValue = next.nodeValue;
    return;
  }
  for (const attr of Array.from(node.attributes)) {
    if (!next.hasAttribute(attr.name)) node.removeAttribute(attr.name);
  }
  for (const attr of next.attributes) {
    if (node.getAttribute(attr.name) !== attr.value) node.setAttribute(attr.name, attr.value);
  }
  const old = Array.from(node.childNodes);
  const local = new Map(old.filter(key).map((child) => [key(child), child]));
  const used = new Set();
  let cursor = node.firstChild;
  for (const child of Array.from(next.childNodes)) {
    const id = key(child);
    let match = id ? items.get(id) || local.get(id) : old.find((candidate) =>
      !key(candidate) && !used.has(candidate) && shape(candidate) === shape(child));
    if (!match || match.nodeName !== child.nodeName) match = child.cloneNode(false);
    used.add(match);
    patch(match, child, items);
    if (match !== cursor) node.insertBefore(match, cursor);
    cursor = match.nextSibling;
  }
  for (const child of old) {
    if (!used.has(child) && child.parentNode === node) child.remove();
  }
}

function visibleItems(scroller, selector, axis) {
  const bounds = scroller.getBoundingClientRect();
  const top = Math.max(0, bounds.top), left = Math.max(0, bounds.left);
  const bottom = Math.min(innerHeight, bounds.bottom), right = Math.min(innerWidth, bounds.right);
  return Array.from(scroller.querySelectorAll(selector)).flatMap((node) => {
    const rect = node.getBoundingClientRect();
    if (rect.bottom <= top || rect.top >= bottom || rect.right <= left || rect.left >= right) return [];
    return [{ node, column: node.closest("[data-drop-column]"), offset: rect[axis] - bounds[axis] }];
  });
}

function captureScroll(page) {
  const view = page.closest(".view");
  return [view, ...page.querySelectorAll(".board-main, .board-canvas, .column-cards, .project-activity-feed")].filter((node) => node?.getClientRects().length).map((node) => ({
    node, top: node.scrollTop, left: node.scrollLeft,
    vertical: node.scrollHeight > node.clientHeight
      ? visibleItems(node, '[data-drag="card"]', "top") : [],
    horizontal: node.classList.contains("board-canvas")
      ? visibleItems(node, "[data-drop-column]", "left") : [],
  }));
}

function restoreScroll(positions) {
  // Restore inner scrollers first, then keep the page's reading position stable.
  for (const { node, top, left, vertical, horizontal } of positions.reverse()) {
    if (!node.isConnected) continue;
    node.scrollTop = top;
    node.scrollLeft = left;
    const anchor = vertical.find((item) => node.contains(item.node) &&
      item.node.closest("[data-drop-column]") === item.column);
    if (anchor) node.scrollTop += anchor.node.getBoundingClientRect().top - node.getBoundingClientRect().top - anchor.offset;
    const column = horizontal.find((item) => node.contains(item.node));
    if (column) node.scrollLeft += column.node.getBoundingClientRect().left - node.getBoundingClientRect().left - column.offset;
  }
}

export function updateBoardDOM(page, next) {
  if (page.isEqualNode(next)) return;
  const positions = captureScroll(page);
  const items = new Map(Array.from(page.querySelectorAll(ITEMS), (node) => [key(node), node]));
  patch(page, next, items);
  restoreScroll(positions);
}
