const PATHS = {
  plus: '<path d="M12 5v14M5 12h14"/>',
  bell: '<path d="M6 9a6 6 0 1 1 12 0c0 7 3 7 3 7H3s3 0 3-7"/><path d="M10 19a2 2 0 0 0 4 0"/>',
  search: '<circle cx="11" cy="11" r="6"/><path d="m20 20-3.5-3.5"/>',
  board: '<rect x="3" y="4" width="5" height="16" rx="1.4"/><rect x="10" y="4" width="5" height="10" rx="1.4"/><rect x="17" y="4" width="4" height="7" rx="1.4"/>',
  tasks: '<path d="m3 6 2 2 3-3M11 7h10M3 13l2 2 3-3M11 14h10M11 21h10"/>',
  check: '<path d="m5 12 5 5L20 7"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h10"/>',
  grip: '<path d="M9 6h.01M9 12h.01M9 18h.01M15 6h.01M15 12h.01M15 18h.01"/>',
  calendar: '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M8 3v4M16 3v4M4 10h16"/>',
  user: '<circle cx="12" cy="8" r="3"/><path d="M5 19c1.5-3 3.8-4.5 7-4.5S17.5 16 19 19"/>',
  trash: '<path d="M4 7h16M9 7V5h6v2M7 7l1 13h8l1-13"/>',
  archive: '<path d="M3 7h18v4H3zM5 11v8h14v-8"/><path d="M10 15h4"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M18.4 5.6 17 7M7 17l-1.4 1.4"/>',
  comment: '<path d="M5 6h14v9H8l-3 3z"/>',
  paperclip: '<path d="m8 12 6.5-6.5a3 3 0 0 1 4 4L11 17a4 4 0 0 1-6-6l8-8"/>',
  logout: '<path d="M10 7V5H5v14h5v-2"/><path d="M10 12h9M16 8l4 4-4 4"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  info: '<circle cx="12" cy="12" r="8"/><path d="M12 11v5M12 8h.01"/>',
  "chevron-down": '<path d="M6 9l6 6 6-6"/>',
};

export function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.classList.add("icon");
  svg.innerHTML = PATHS[name] || "";
  return svg;
}
