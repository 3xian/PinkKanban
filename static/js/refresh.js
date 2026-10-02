// The page owns which interactions and nested scrollers can start a refresh.
export function allowsPullRefresh(element, scrollingElement) {
  if (!element) return false;
  for (let node = element; node; node = node.parentElement) {
    if (node.isContentEditable || node.matches(
      'button, a, input, textarea, select, label, [draggable=true], [data-drag], [data-drop-column]',
    )) return false;
    if (node !== scrollingElement && node.scrollHeight > node.clientHeight &&
        /auto|scroll/.test(getComputedStyle(node).overflowY)) return false;
  }
  return true;
}

// Coordinates are fractions of the native WebView's visible bounds.
export function canPullRefreshAt(x, y) {
  const viewport = window.visualViewport;
  const clientX = (viewport?.offsetLeft ?? 0) + x * (viewport?.width ?? window.innerWidth);
  const clientY = (viewport?.offsetTop ?? 0) + y * (viewport?.height ?? window.innerHeight);
  return allowsPullRefresh(document.elementFromPoint(clientX, clientY), document.scrollingElement);
}
