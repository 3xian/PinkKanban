import { api } from "./api.js";
import { installDrag } from "./dnd.js";
import { ACTIONS, COLORS, PRIORITIES, ROLES, avatar, canAdmin, canEdit, dueInfo, el, fileSize, markdown, relative, safeColor } from "./format.js";
import { icon as glyph } from "./icons.js";

const state = {
  user: null,
  view: "projects",
  projects: [],
  archivedProjects: [],
  showArchived: false,
  quota: { used: 0, limit: 30, remaining: 30 },
  unread: 0,
  projectId: null,
  board: null,
  settings: null,
  activity: [],
  cardId: null,
  detail: null,
  tasks: [],
  notes: [],
  filters: { q: "", mine: false, overdue: false, label: "", priority: "", hideDone: false, archived: false },
  sidebar: false,
  modal: null,
  compose: null,
  dragging: false,
  authMode: "login",
  codeWait: 0,
  color: COLORS[0],
  pendingCard: null,
};

const app = document.getElementById("app");
const drawer = document.getElementById("drawer");
const modal = document.getElementById("modal");
const toasts = document.getElementById("toasts");

function toast(message) {
  const node = el("div", { class: "toast" }, glyph("info"), el("span", { text: message }));
  toasts?.append(node);
  setTimeout(() => node.remove(), 3200);
}

function go(hash) {
  if (location.hash === hash) route();
  else location.hash = hash;
}

function editable() {
  return state.board && canEdit(state.board.role, state.board.project.archived);
}

function filtersOn() {
  const f = state.filters;
  return Boolean(f.q || f.mine || f.overdue || f.label || f.priority || f.hideDone || f.archived);
}

function toggleFilterPop(trigger) {
  const pop = trigger.querySelector(".filter-pop");
  if (!pop) return;
  const wasOpen = !pop.hidden;
  closeFilterPops();
  if (wasOpen) return;
  pop.hidden = false;
  trigger.setAttribute("aria-expanded", "true");
  trigger.classList.add("is-open");
  for (const item of pop.querySelectorAll(".filter-item")) {
    if (item.classList.contains("is-on")) item.focus({ preventScroll: true });
    break;
  }
}

function closeFilterPops() {
  for (const pop of document.querySelectorAll(".filter-pop")) pop.hidden = true;
  for (const trigger of document.querySelectorAll(".filter-trigger")) {
    trigger.setAttribute("aria-expanded", "false");
    trigger.classList.remove("is-open");
  }
}

document.addEventListener("click", (event) => {
  if (!event.target.closest(".filter-trigger")) closeFilterPops();
});
function paintFilterLock() {
  const note = document.querySelector("[data-filter-lock]");
  if (note) note.hidden = !filtersOn();
}

function findCard(id) {
  for (const column of state.board?.columns || []) {
    const card = column.cards.find((item) => item.id === id);
    if (card) return card;
  }
  return null;
}

function visible(card) {
  const f = state.filters;
  if (card.archived && !f.archived) return false;
  if (!card.archived && f.archived) return true;
  if (f.mine && !card.assignee_ids.includes(state.user.id)) return false;
  if (f.overdue && !dueInfo(card.due_on)?.over) return false;
  if (f.label && !card.label_ids.includes(Number(f.label))) return false;
  if (f.priority && card.priority !== f.priority) return false;
  if (f.hideDone && card.done) return false;
  if (f.q) {
    const q = f.q.toLowerCase();
    if (!`${card.title} ${card.excerpt || ""}`.toLowerCase().includes(q)) return false;
  }
  return true;
}

export async function boot() {
  try {
    const data = await api("/api/bootstrap");
    applyBootstrap(data);
  } catch (error) {
    if (error.status !== 401) throw error;
    state.user = null;
  }
  // Use the projects included in bootstrap only for this initial navigation.
  try {
    let hash;
    let useBootstrap = true;
    do {
      hash = location.hash;
      try {
        await route({ useBootstrap });
      } catch (error) {
        // An obsolete deep link must not hide the user's newer destination.
        if (hash === location.hash) throw error;
      }
      useBootstrap = false;
    } while (hash !== location.hash);
  } finally {
    // Keep navigation recoverable even when an initial deep link fails.
    window.addEventListener("hashchange", () => { route().catch((error) => toast(error.message)); });
    setInterval(poll, 8000);
  }
}

function applyBootstrap(data) {
  state.user = data.user;
  state.projects = data.projects;
  state.unread = data.unread;
  state.quota = data.quota;
}

async function poll() {
  if (!state.user || document.hidden || state.dragging) return;
  if (document.activeElement?.closest("input, textarea, #drawer, #modal")) return;
  try {
    const notes = await api("/api/notifications");
    state.unread = notes.unread;
    paintBadges();
    if (state.view === "board" && state.projectId) {
      state.board = await api(`/api/projects/${state.projectId}/board`);
      paintCanvas();
    }
  } catch (error) {
    if (error.status === 401) {
      state.user = null;
      render();
    }
  }
}

async function route({ useBootstrap = false } = {}) {
  if (!state.user) {
    render();
    return;
  }
  const [name, id] = (location.hash.replace(/^#\/?/, "") || "projects").split("/");
  if (name === "board" && id) return openBoard(Number(id));
  if (name === "settings" && id) return openSettings(Number(id));
  if (name === "tasks") return openTasks();
  if (name === "notifications") return openNotes();
  if (name === "account") {
    state.view = "account";
    render();
    return;
  }
  state.view = "projects";
  if (!useBootstrap || state.showArchived) await loadProjects();
  render();
}

async function loadProjects() {
  const data = await api(`/api/projects?archived=${state.showArchived ? "true" : "false"}`);
  if (state.showArchived) state.archivedProjects = data.projects;
  else state.projects = data.projects;
  state.quota = data.quota;
}

async function openBoard(id) {
  state.projectId = id;
  state.view = "board";
  state.cardId = null;
  drawer.hidden = true;
  state.board = await api(`/api/projects/${id}/board`);
  const pending = state.pendingCard;
  state.pendingCard = null;
  render();
  if (pending && state.view === "board" && state.projectId === id) await openCard(pending);
}

async function openSettings(id) {
  state.projectId = id;
  state.view = "settings";
  state.settings = await api(`/api/projects/${id}`);
  state.activity = (await api(`/api/projects/${id}/activity`)).items;
  render();
}

async function openTasks() {
  state.view = "tasks";
  state.tasks = (await api("/api/me/cards")).cards;
  render();
}

async function openNotes() {
  state.view = "notifications";
  const data = await api("/api/notifications");
  state.notes = data.items;
  state.unread = data.unread;
  render();
}

async function openCard(id) {
  state.cardId = id;
  state.detail = await api(`/api/cards/${id}`);
  paintDrawer();
}

function closeDrawer() {
  state.cardId = null;
  state.detail = null;
  drawer.hidden = true;
  drawer.replaceChildren();
}

function render() {
  const authed = Boolean(state.user);
  document.body.classList.toggle("is-auth", !authed);
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", "#080b12");
  app.replaceChildren(authed ? shell() : authView());
  if (!authed) startAuthMotion(app.querySelector(".auth"));
  paintBadges();
  if (state.cardId) paintDrawer();
  else drawer.hidden = true;
  paintModal();
  document.querySelector("[data-autofocus]")?.focus();
}

function authView() {
  const login = state.authMode === "login";
  const count = window.innerWidth < 760 ? 8 : 18;
  return el("div", { class: "auth" },
    el("div", { class: "auth-glow" }),
    el("div", { class: "auth-scene" },
      el("div", { class: "auth-world" },
        el("div", { class: "auth-orb" }),
        el("div", { class: "auth-orb o2" }),
        ...spacePositions(count).map((pos, index) => spaceBoard(index, pos)),
      ),
    ),
    el("div", { class: "auth-vignette" }),
    el("div", { class: "auth-noise" }),
    el("header", { class: "auth-bar" },
      el("div", { class: "auth-brand" }, mark(), "看板", el("small", { text: "多人任务协作" })),
    ),
    el("form", { class: "auth-card", "data-form": "auth" },
      el("h2", { text: login ? "欢迎回来" : "创建账号" }),
      el("p", { class: "lede", text: login ? "从上次停下的地方继续。" : "验证码会发到这个邮箱，10 分钟内有效。" }),
      el("div", { class: "seg" },
        el("button", { type: "button", class: login ? "is-on" : "", "data-act": "auth-mode", "data-mode": "login", text: "登录" }),
        el("button", { type: "button", class: login ? "" : "is-on", "data-act": "auth-mode", "data-mode": "register", text: "注册" }),
      ),
      field("邮箱", "email", "email", "you@example.com"),
      login ? null : codeField(),
      login ? null : field("显示名", "display_name", "text", "怎么称呼你"),
      field("密码", "password", "password", login ? "你的密码" : "至少 8 位"),
      el("button", { class: "btn-primary btn-block", type: "submit", text: login ? "进入看板" : "用邮箱注册" }),
    ),
    el("div", { class: "auth-hint", text: "MOVE · SCROLL · EXPLORE" }),
  );
}

function codeField() {
  return el("label", { class: "field" }, "验证码",
    el("div", { class: "code-row" },
      el("input", { name: "code", type: "text", inputmode: "numeric", autocomplete: "one-time-code", placeholder: "6 位数字", required: true, maxlength: "6", pattern: "\\d{6}" }),
      el("button", { type: "button", class: "btn btn-ghost", "data-act": "send-code", disabled: state.codeWait > 0, text: state.codeWait > 0 ? `${state.codeWait}s` : "获取验证码" }),
    ),
  );
}

let codeTimer = 0;

function startCodeWait(seconds) {
  state.codeWait = seconds;
  clearInterval(codeTimer);
  paintCodeWait();
  codeTimer = setInterval(() => {
    state.codeWait = Math.max(0, state.codeWait - 1);
    paintCodeWait();
    if (state.codeWait === 0) clearInterval(codeTimer);
  }, 1000);
}

function paintCodeWait() {
  const button = document.querySelector("[data-act=send-code]");
  if (!button) return;
  button.textContent = state.codeWait > 0 ? `${state.codeWait}s` : "获取验证码";
  button.disabled = state.codeWait > 0;
}

const SPACE_TITLES = ["产品发布", "设计系统", "增长冲刺", "移动端", "研究笔记", "上线清单", "品牌刷新", "数据分析"];
const SPACE_TASKS = ["梳理路径", "补齐状态", "同步变量", "准备素材", "修复边缘", "定义指标"];
const SPACE_ACCENTS = ["#8b7cff", "#55d9ff", "#ff73ba", "#65e6b6", "#ffba6a"];

function seeded(n) {
  const x = Math.sin(n * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

function spacePositions(count) {
  const positions = [];
  for (let i = 0; i < count; i += 1) {
    const ring = i < 8 ? 1 : i < 14 ? 2 : 3;
    const angle = i * 0.91 + ring * 0.42;
    let x = Math.cos(angle) * (420 + ring * 230 + seeded(i + 1) * 150);
    let y = Math.sin(angle * 1.11) * (220 + ring * 120 + seeded(i + 5) * 100);
    if (i % 6 === 0) x *= 0.72;
    if (i % 8 === 0) y *= 0.68;
    positions.push({
      x, y, z: -220 - ring * 280 + seeded(i + 9) * 460,
      rx: -8 + seeded(i + 2) * 18,
      ry: -22 + seeded(i + 4) * 44,
      rz: -7 + seeded(i + 8) * 14,
      scale: (0.78 + seeded(i + 6) * 0.34).toFixed(2),
      delay: (-i * 0.27).toFixed(2),
      drift: 12 + Math.floor(seeded(i + 3) * 22),
    });
  }
  return positions.sort((a, b) => a.z - b.z);
}

function spaceBoard(index, pos) {
  const accent = SPACE_ACCENTS[index % SPACE_ACCENTS.length];
  const board = el("article", {
    class: "space-board",
    style: `--x:${pos.x}px;--y:${pos.y}px;--z:${pos.z}px;--rx:${pos.rx}deg;--ry:${pos.ry}deg;--rz:${pos.rz}deg;--scale:${pos.scale};--delay:${pos.delay}s;--drift:${pos.drift}px`,
  },
    el("div", { class: "space-head" },
      el("div", { class: "space-title", text: SPACE_TITLES[index % SPACE_TITLES.length] }),
      el("div", { class: "space-meta" }, el("span", { class: "space-faces" }, el("i"), el("i"), el("i")), el("span", { text: String(3 + (index % 5)) })),
    ),
    el("div", { class: "space-cols" },
      ...["待办", "进行", "完成"].map((name, column) => el("div", { class: "space-col" },
        el("div", { class: "space-col-head" }, el("span", { text: name }), el("span", { text: String(1 + ((index + column) % 3)) })),
        spaceTask(index * 3 + column, accent),
      )),
    ),
  );
  board.style.opacity = String(Math.max(0.28, Math.min(0.94, 1 - Math.abs(pos.z) / 2200)));
  return board;
}

function spaceTask(index, accent) {
  const progress = 24 + Math.floor(seeded(index * 3.17) * 72);
  return el("div", { class: "space-task", style: `--accent:${accent};--p:${progress}%` },
    el("div", { class: "space-task-title", text: SPACE_TASKS[index % SPACE_TASKS.length] }),
    el("div", { class: "space-progress" }, el("span")),
  );
}

let authMotion = 0;
let spaceX = 0;
let spaceY = 0;
let spaceZ = 0;
let spaceTargetX = 0;
let spaceTargetY = 0;
let spaceTargetZ = 0;

function startAuthMotion(root) {
  cancelAnimationFrame(authMotion);
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const glow = root.querySelector(".auth-glow");
  const onMove = (event) => {
    spaceTargetX = (event.clientX / innerWidth - 0.5) * 2;
    spaceTargetY = (event.clientY / innerHeight - 0.5) * 2;
    if (glow) {
      glow.style.left = `${event.clientX}px`;
      glow.style.top = `${event.clientY}px`;
    }
  };
  const onWheel = (event) => {
    if (!root.isConnected || event.target.closest(".auth-card")) return;
    spaceTargetZ = Math.max(-2.2, Math.min(2.2, spaceTargetZ + event.deltaY * 0.0015));
  };
  window.addEventListener("pointermove", onMove);
  window.addEventListener("wheel", onWheel, { passive: true });
  const tick = () => {
    if (!root.isConnected) {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("wheel", onWheel);
      return;
    }
    if (!reduce) {
      spaceX += (spaceTargetX - spaceX) * 0.055;
      spaceY += (spaceTargetY - spaceY) * 0.055;
      spaceZ += (spaceTargetZ - spaceZ) * 0.06;
      root.style.setProperty("--mx", spaceX.toFixed(4));
      root.style.setProperty("--my", spaceY.toFixed(4));
      root.style.setProperty("--scroll", spaceZ.toFixed(4));
    }
    authMotion = requestAnimationFrame(tick);
  };
  authMotion = requestAnimationFrame(tick);
}

function mark() {
  return el("img", { class: "mark", src: "/static/favicon.svg", alt: "", width: "28", height: "28" });
}

function field(label, name, type, placeholder) {
  return el("label", { class: "field" }, label, el("input", { name, type, placeholder, required: true, autocomplete: name === "password" ? "current-password" : "email" }));
}

function shell() {
  return el("div", { class: "shell" },
    el("aside", { class: state.sidebar ? "sidebar is-open" : "sidebar" },
      el("div", { class: "brand" }, mark(), el("span", { class: "brand-copy" }, el("strong", { text: "看板" }), el("small", { text: "多人任务协作" }))),
      el("nav", { class: "side-nav" },
        nav("projects", "项目", "board"),
        nav("tasks", "我的任务", "tasks"),
        nav("notifications", "通知", "bell", true),
      ),
      el("div", { class: "side-label", text: "最近" }),
      el("div", { class: "side-projects" }, ...state.projects.slice(0, 12).map((project) => {
        const link = el("button", { class: project.id === state.projectId ? "project-link is-on" : "project-link", "data-act": "open-project", "data-id": project.id });
        const dot = el("i", { class: "dot" });
        dot.style.setProperty("--c", safeColor(project.color));
        link.append(dot, el("span", { text: project.name }));
        return link;
      })),
      el("div", { class: "side-foot" },
        el("button", { class: "user-chip", "data-act": "nav", "data-view": "account" }, avatar(state.user), el("span", {}, el("strong", { text: state.user.display_name }), el("small", { text: state.user.email }))),
      ),
    ),
    state.sidebar ? el("button", { class: "backdrop", "data-act": "close-side", "aria-label": "关闭菜单" }) : null,
    el("div", { class: "main" },
      el("button", { class: "icon-btn floating-menu", "data-act": "toggle-side", "aria-label": "菜单" }, glyph("menu")),
      el("div", { class: "view" }, viewBody()),
    ),
    el("nav", { class: "tabbar" },
      tab("projects", "项目", "board"),
      tab("board", "看板", "board"),
      tab("tasks", "任务", "tasks"),
      tab("notifications", "通知", "bell"),
    ),
  );
}

function nav(view, label, iconName, badge = false) {
  return el("button", { class: state.view === view ? "nav-btn is-on" : "nav-btn", "data-act": "nav", "data-view": view }, glyph(iconName), el("span", { text: label }), badge ? el("span", { class: "badge", "data-badge": "1", text: state.unread ? String(state.unread) : "" }) : null);
}

function tab(view, label, iconName) {
  const button = el("button", { class: state.view === view ? "is-on" : "", "data-act": "nav", "data-view": view }, glyph(iconName), label);
  if (view === "notifications") button.append(el("i", { class: "badge", "data-badge": "1", text: state.unread ? String(state.unread) : "" }));
  return button;
}

function viewBody() {
  if (state.view === "board") return boardView();
  if (state.view === "tasks") return tasksView();
  if (state.view === "notifications") return notesView();
  if (state.view === "settings") return settingsView();
  if (state.view === "account") return accountView();
  return projectsView();
}

function projectsView() {
  const list = state.showArchived ? state.archivedProjects : state.projects;
  return el("section", {},
    el("div", { class: "page-head" },
      el("div", {}, el("h2", { text: state.showArchived ? "归档" : "项目" }), el("p", { text: `今天还可创建 ${state.quota.remaining} / ${state.quota.limit} 个` })),
      el("div", { class: "page-actions" },
        el("button", { class: "btn-ghost", "data-act": "toggle-archived", text: state.showArchived ? "返回项目" : "已归档" }),
        el("button", { class: "btn-primary", "data-act": "new-project", disabled: state.quota.remaining <= 0 }, glyph("plus"), el("span", { text: "新建" })),
      ),
    ),
    list.length ? el("div", { class: "project-grid" }, ...list.map(projectCard)) : emptyState("还没有项目", "建一个，从第一张卡片开始。"),
  );
}

function emptyState(title, body) {
  return el("div", { class: "empty" }, el("div", { class: "empty-mark" }, glyph("board")), el("strong", { text: title }), body ? el("p", { text: body }) : null);
}

function projectCard(project) {
  const card = el("button", { class: "project-card", "data-act": "open-project", "data-id": project.id });
  card.style.setProperty("--c", safeColor(project.color));
  const dot = el("i", { class: "dot" });
  dot.style.setProperty("--c", safeColor(project.color));
  const go = glyph("arrow");
  go.classList.add("project-go");
  card.append(
    el("div", { class: "project-top" }, dot, el("strong", { text: project.name }), go),
    el("p", { text: project.description || "没有简介" }),
    el("div", { class: "project-foot" },
      el("span", { text: `${project.open_cards} 张卡片` }),
      el("span", { text: `${project.member_count} 人` }),
      el("span", { class: "project-role", text: ROLES[project.role] || "" }),
    ),
  );
  return card;
}

function boardView() {
  if (!state.board) return emptyState("选择一个项目");
  const project = state.board.project;
  return el("section", { class: "board-page" },
    el("div", { class: "board-head" },
      el("div", {}, el("h2", { text: project.name }), el("p", { class: "muted", text: project.description || "把卡片拖到它该在的位置。" })),
      el("div", { class: "board-people" },
        el("div", { class: "faces" }, ...state.board.members.slice(0, 5).map((person) => avatar(person))),
        el("button", { class: "btn-ghost", "data-act": "open-settings", "data-id": project.id }, glyph("user"), el("span", { text: "成员" })),
      ),
    ),
    el("div", { class: "filters" },
      el("label", { class: "search-wrap" }, glyph("search"), el("input", { class: "search", id: "board-search", placeholder: "搜索卡片", value: state.filters.q, "aria-label": "搜索卡片" })),
      el("div", { class: "filter-chips" }, chip("mine", "我的"), chip("overdue", "延期"), chip("hideDone", "隐藏完成"), chip("archived", "归档")),
      filterSelect("filter-label", "标签", [
        { value: "", label: "全部标签" },
        ...state.board.labels.map((label) => ({ value: label.id, label: label.name })),
      ], state.filters.label),
      filterSelect("filter-priority", "优先级", [
        { value: "", label: "全部优先级" },
        ...PRIORITIES.filter(([value]) => value !== "none").map(([value, label]) => ({ value, label })),
      ], state.filters.priority),
      el("span", { class: "filter-note", "data-filter-lock": "1", hidden: !filtersOn() }, glyph("info"), "筛选开启时暂停拖拽"),
    ),
    canvasNode(),
  );
}

function chip(key, label) {
  return el("button", { class: state.filters[key] ? "chip is-on" : "chip", "data-act": "filter", "data-key": key, text: label });
}

function filterSelect(id, kind, options, current) {
  const selected = options.find((opt) => String(opt.value) === String(current || "")) || options[0];
  const trigger = el("button", {
    type: "button",
    class: "filter-trigger",
    id,
    "data-act": "filter-select",
    "data-filter": id,
    "aria-haspopup": "listbox",
    "aria-expanded": "false",
    "aria-label": kind,
  },
    glyph("chevron-down"),
    el("span", { class: "filter-trigger-text", text: selected.label }),
  );
  const list = el("ul", { class: "filter-pop", role: "listbox", hidden: true },
    ...options.map((opt) => {
      const on = String(opt.value) === String(current || "");
      return el("li", {
        role: "option",
        tabindex: "-1",
        class: on ? "filter-item is-on" : "filter-item",
        "data-act": "filter-pick",
        "data-filter": id,
        "data-value": String(opt.value),
        "aria-selected": on ? "true" : "false",
        text: opt.label,
      });
    }),
  );
  trigger.append(list);
  return trigger;
}

function canvasNode() {
  const node = el("div", { class: "board-canvas", id: "board-canvas" });
  for (const column of state.board.columns) node.append(columnNode(column));
  if (editable()) node.append(el("button", { class: "add-column", "data-act": "new-column" }, glyph("plus"), el("span", { text: "添加列表" })));
  return node;
}

function paintCanvas() {
  const old = document.getElementById("board-canvas");
  if (!old || !state.board) return;
  const left = old.scrollLeft;
  const next = canvasNode();
  old.replaceWith(next);
  next.scrollLeft = left;
}

function columnNode(column) {
  const cards = column.cards.filter(visible);
  const live = column.cards.filter((card) => !card.archived);
  const node = el("section", { class: "column", "data-drop-column": column.id });
  const dot = el("i", { class: "col-dot" });
  dot.style.setProperty("--c", safeColor(column.color));
  const over = Boolean(column.wip_limit && live.length > column.wip_limit);
  const head = el("div", { class: "column-head" },
    editable() ? el("button", { class: "grip", "data-drag": "column", "data-id": column.id, "aria-label": "拖动列表" }, glyph("grip")) : null,
    dot,
    el("strong", { text: column.name }),
    el("span", { class: over ? "wip is-over" : "count", text: column.wip_limit ? `${live.length} / ${column.wip_limit}` : String(live.length) }),
    el("span", { class: "spacer" }),
    editable() ? el("button", { class: "icon-btn icon-btn-sm", "data-act": "edit-column", "data-id": column.id, "aria-label": "列表设置" }, glyph("settings")) : null,
  );
  const body = el("div", { class: "column-cards" });
  for (const card of cards) body.append(cardNode(card, column));
  node.append(head, body);
  if (editable() && !state.filters.archived) {
    if (state.compose?.columnId === column.id) {
      node.append(el("form", { class: "composer", "data-form": "card" },
        el("input", { name: "title", placeholder: "卡片标题", "data-autofocus": "1", required: true }),
        el("input", { type: "hidden", name: "column_id", value: column.id }),
        el("button", { class: "btn-primary btn-tiny", text: "添加" }),
      ));
    } else node.append(el("button", { class: "add-card", "data-act": "compose", "data-column": column.id }, glyph("plus"), el("span", { text: "添加卡片" })));
  }
  return node;
}

const PRIORITY_ACCENT = { low: "#5aa7c8", medium: "#e0a15a", high: "#8b72ff", urgent: "#ff73ba" };

function priorityLabel(priority) {
  return PRIORITIES.find(([value]) => value === priority)?.[1] || "";
}

function metaBit(name, text, extra = "") {
  return el("span", { class: extra ? `meta-bit ${extra}` : "meta-bit" }, glyph(name), text);
}

function cardNode(card, column) {
  const due = dueInfo(card.due_on);
  const accent = /^#[0-9A-Fa-f]{6}$/.test(card.cover_color || "") ? card.cover_color : (PRIORITY_ACCENT[card.priority] || "");
  const node = el("article", {
    class: `card${card.done ? " is-done" : ""}${card.archived ? " is-archived" : ""}${accent ? " has-mark" : ""}`,
    "data-drag": "card",
    "data-id": card.id,
    "data-column": column.id,
  });
  if (accent) node.style.setProperty("--c", accent);
  const labels = state.board.labels.filter((label) => card.label_ids.includes(label.id));
  const head = el("div", { class: "card-head" }, el("h3", { class: "card-title", text: card.title }));
  if (card.priority && card.priority !== "none") head.append(el("span", { class: `prio-mark prio-${card.priority}`, text: priorityLabel(card.priority) }));
  node.append(head);
  if (labels.length) node.append(el("div", { class: "pills" }, ...labels.map((label) => {
    const pill = el("span", { class: "pill", text: label.name });
    pill.style.setProperty("--c", safeColor(label.color));
    return pill;
  })));
  const bits = [];
  if (due) bits.push(metaBit("calendar", due.text, due.over ? "due is-over" : due.today ? "due is-today" : "due"));
  if (card.checklist.total) bits.push(metaBit("check", `${card.checklist.done}/${card.checklist.total}`));
  if (card.comment_count) bits.push(metaBit("comment", String(card.comment_count)));
  const people = state.board.members.filter((person) => card.assignee_ids.includes(person.id)).slice(0, 3);
  if (bits.length || people.length) node.append(el("div", { class: "card-foot" }, ...bits, el("span", { class: "spacer" }), ...people.map((person) => avatar(person))));
  return node;
}

function tasksView() {
  const groups = [
    ["延期", state.tasks.filter((card) => dueInfo(card.due_on)?.over && !card.done)],
    ["今天", state.tasks.filter((card) => dueInfo(card.due_on)?.today && !card.done)],
    ["之后", state.tasks.filter((card) => !dueInfo(card.due_on)?.over && !dueInfo(card.due_on)?.today)],
  ];
  return el("section", {},
    el("div", { class: "page-head" }, el("div", {}, el("h2", { text: "我的任务" }), el("p", { text: "指派给你、尚未归档的卡片。" }))),
    ...groups.map(([title, cards]) => el("div", { class: "section task-group" }, el("h3", { text: title }), cards.length ? el("div", { class: "task-list" }, ...cards.map(taskRow)) : el("p", { class: "muted", text: "没有" }))),
  );
}

function taskRow(card) {
  const due = dueInfo(card.due_on);
  const mark = el("i", { class: "task-mark" });
  mark.style.setProperty("--c", safeColor(card.project_color));
  return el("button", { class: "task", "data-act": "open-task", "data-id": card.id, "data-project": card.project_id },
    mark,
    el("span", { class: "task-main" }, el("strong", { text: card.title }), el("span", { class: "muted", text: `${card.project_name} · ${card.column_name}` })),
    due ? el("span", { class: due.over ? "due is-over" : due.today ? "due is-today" : "muted", text: due.text }) : null,
  );
}

function notesView() {
  return el("section", {},
    el("div", { class: "page-head" },
      el("div", {}, el("h2", { text: "通知" }), el("p", { text: "邀请需要你批准后才会加入项目。" })),
      el("button", { class: "btn-ghost", "data-act": "read-all", text: "全部已读" }),
    ),
    state.notes.length ? el("div", { class: "note-list" }, ...state.notes.map(noteRow)) : emptyState("没有新消息"),
  );
}

function noteRow(note) {
  const pending = note.type === "project_invite" && note.status === "pending";
  return el("article", { class: note.read ? "note" : "note is-unread" },
    el("i", { class: "note-dot" }),
    el("div", { class: "note-main" },
      el("header", {}, note.actor ? avatar(note.actor) : glyph("bell"), el("strong", { text: note.title }), el("span", { class: "muted", text: relative(note.created_at) })),
      note.body ? el("p", { text: note.body }) : null,
      pending ? el("div", { class: "row" },
        el("button", { class: "btn-primary btn-tiny", "data-act": "accept", "data-id": note.id, text: "批准" }),
        el("button", { class: "btn-ghost btn-tiny", "data-act": "reject", "data-id": note.id, text: "拒绝" }),
      ) : el("span", { class: "muted", text: { accepted: "已接受", rejected: "已拒绝", cancelled: "已撤回", info: "" }[note.status] || "" }),
    ),
  );
}

function activityList(items) {
  if (!items?.length) return el("p", { class: "muted", text: "还没有动态" });
  return el("div", { class: "timeline" }, ...items.map((item) => el("div", { class: "tl-item" },
    el("i", { class: "tl-dot" }),
    el("div", {},
      el("div", { class: "tl-text" }, el("strong", { text: item.user?.display_name || "有人" }), " ", ACTIONS[item.action] || item.action, item.detail?.title ? `「${item.detail.title}」` : ""),
      el("div", { class: "muted", text: relative(item.created_at) }),
    ),
  )));
}

function settingsView() {
  const data = state.settings;
  if (!data) return el("p", { text: "加载中" });
  const admin = canAdmin(data.role);
  const owner = data.role === "owner";
  return el("section", { class: "settings-grid" },
    el("div", { class: "settings-main" },
      el("div", { class: "page-head" }, el("div", {}, el("h2", { text: "项目设置" }), el("p", { text: data.project.name }))),
      el("div", { class: "settings-block" },
        el("h3", { text: "常规" }),
        admin ? el("form", { "data-form": "project-save" },
          el("label", { class: "field" }, "名称", el("input", { name: "name", value: data.project.name, required: true })),
          el("label", { class: "field" }, "简介", el("textarea", { name: "description", text: data.project.description })),
          el("div", { class: "field" }, "颜色", colorPicker(data.project.color)),
          el("button", { class: "btn-primary", text: "保存项目" }),
        ) : el("p", { text: data.project.description || "没有简介" }),
      ),
      el("div", { class: "settings-block" }, el("h3", { text: "成员" }), el("div", { class: "member-list" }, ...data.members.map((person) => memberRow(person, data)))),
      admin ? el("form", { class: "settings-block", "data-form": "invite" },
        el("h3", { text: "邀请" }),
        el("label", { class: "field" }, "对方邮箱", el("input", { name: "email", type: "email", placeholder: "已注册的邮箱", required: true })),
        el("label", { class: "field" }, "角色", el("select", { name: "role" }, el("option", { value: "member", text: "成员" }), el("option", { value: "admin", text: "管理员" }), el("option", { value: "viewer", text: "只读" }))),
        el("button", { class: "btn-primary", text: "发送站内邀请" }),
      ) : null,
      data.invites?.length ? el("div", { class: "settings-block" }, el("h3", { text: "等待批准" }), el("div", { class: "invite-list" }, ...data.invites.map((invite) => el("div", { class: "invite-row" }, el("span", { text: `${invite.display_name} · ${invite.email}` }), el("span", { class: "spacer" }), el("button", { class: "btn-tiny", "data-act": "cancel-invite", "data-id": invite.id, text: "撤回" }))))) : null,
      el("div", { class: "settings-block" },
        el("div", { class: "danger-zone" },
          el("h3", { text: "危险操作" }),
          owner ? null : el("button", { class: "btn-ghost", "data-act": "leave", text: "退出项目" }),
          admin ? el("button", { class: "btn-ghost", "data-act": data.project.archived ? "restore-project" : "archive-project", text: data.project.archived ? "恢复项目" : "归档项目" }) : null,
          owner ? el("button", { class: "btn-danger", "data-act": "delete-project", text: "删除项目" }) : null,
        ),
      ),
    ),
    el("aside", { class: "settings-side" }, el("h3", { text: "动态" }), activityList(state.activity.slice(0, 30))),
  );
}

function memberRow(person, data) {
  const admin = canAdmin(data.role);
  const mine = person.id === state.user.id;
  return el("div", { class: "member-row" },
    avatar(person),
    el("div", { class: "member-main" }, el("strong", { text: person.display_name }), el("div", { class: "muted", text: person.email })),
    el("div", { class: "member-actions" },
      person.role === "owner" ? el("span", { class: "role-label", text: "拥有者" }) : admin && !mine ? el("select", { class: "role-select", "data-act": "role", "data-id": person.id }, ...["admin", "member", "viewer"].map((role) => el("option", { value: role, text: ROLES[role], selected: person.role === role }))) : el("span", { class: "role-label", text: ROLES[person.role] }),
      data.role === "owner" && !mine ? el("button", { class: "btn-tiny", "data-act": "transfer", "data-id": person.id, text: "移交" }) : null,
      admin && person.role !== "owner" && !mine ? el("button", { class: "btn-tiny btn-danger", "data-act": "remove-member", "data-id": person.id, text: "移除" }) : null,
    ),
  );
}

function accountView() {
  return el("section", { class: "account-page" },
    el("div", { class: "page-head" }, el("div", {}, el("h2", { text: "账号" }), el("p", { text: "资料、密码和当前会话。" }))),
    el("div", { class: "account-id" }, avatar(state.user, "lg"), el("div", {}, el("strong", { text: state.user.display_name }), el("span", { class: "readonly", text: state.user.email }))),
    el("form", { class: "account-block", "data-form": "account" },
      el("h3", { text: "资料" }),
      el("label", { class: "field" }, "显示名", el("input", { name: "display_name", value: state.user.display_name, required: true })),
      el("div", { class: "field" }, "头像颜色", colorPicker(state.user.avatar_color)),
      el("button", { class: "btn-primary", text: "保存" }),
    ),
    el("form", { class: "account-block", "data-form": "password" },
      el("h3", { text: "安全" }),
      el("label", { class: "field" }, "当前密码", el("input", { name: "current_password", type: "password", required: true, autocomplete: "current-password" })),
      el("label", { class: "field" }, "新密码", el("input", { name: "new_password", type: "password", required: true, minlength: "8", autocomplete: "new-password" })),
      el("button", { class: "btn-ghost", text: "更新密码" }),
    ),
    el("div", { class: "account-block" },
      el("h3", { text: "会话" }),
      el("button", { class: "btn-danger", "data-act": "logout", text: "退出登录" }),
    ),
  );
}

function colorPicker(selected) {
  state.color = safeColor(selected, COLORS[0]);
  return el("div", { class: "swatches", "data-swatches": "1" }, ...COLORS.map((color) => {
    const button = el("button", { type: "button", class: color === state.color ? "swatch is-on" : "swatch", "data-act": "pick-color", "data-color": color, "aria-label": color });
    button.style.background = color;
    return button;
  }));
}

function paintDrawer() {
  const data = state.detail;
  if (!data) {
    drawer.hidden = true;
    return;
  }
  const card = data.card;
  const edit = card.can_edit;
  const scroll = drawer.querySelector(".drawer-panel")?.scrollTop || 0;
  const labels = state.board?.labels || [];
  const members = state.board?.members || [];
  drawer.hidden = false;
  drawer.replaceChildren(
    el("button", { class: "drawer-backdrop", "data-act": "close-drawer", "aria-label": "关闭" }),
    el("article", { class: "drawer-panel" },
        el("div", { class: "drawer-top" },
          el("i", { class: "sheet-handle", "aria-hidden": "true" }),
          el("div", { class: "drawer-top-row" },
            el("span", { class: "crumb", text: [state.board?.project?.name, columnName(card.column_id)].filter(Boolean).join(" / ") }),
            el("button", { class: "icon-btn", "data-act": "close-drawer", "aria-label": "关闭" }, glyph("close")),
          ),
          edit ? el("input", { class: "drawer-title", "data-save": "title", value: card.title, "aria-label": "标题" }) : el("h2", { class: "drawer-title", text: card.title }),
        ),
      el("div", { class: "props" },
        el("div", { class: "prop" },
          el("span", { class: "prop-k", text: "优先级" }),
          el("div", { class: "prio" }, ...PRIORITIES.map(([value, label]) => el("button", { type: "button", class: card.priority === value ? "is-on" : "", "data-act": "priority", "data-value": value, disabled: !edit, text: label }))),
        ),
        el("div", { class: "prop" },
          el("span", { class: "prop-k", text: "截止日期" }),
          el("label", { class: "field" }, el("input", { type: "date", "data-save": "due", value: card.due_on || "", disabled: !edit, "aria-label": "截止日期" })),
        ),
        el("div", { class: "prop" },
          el("span", { class: "prop-k", text: "状态" }),
          el("label", { class: "check" }, el("input", { type: "checkbox", "data-act": "done", checked: card.done, disabled: !edit }), "完成"),
        ),
        el("div", { class: "prop prop-top" },
          el("span", { class: "prop-k", text: "指派" }),
          el("div", { class: "assignees" }, ...members.map((person) => {
            const on = card.assignee_ids.includes(person.id);
            return el("button", { type: "button", class: on ? "assignee is-on" : "assignee", "data-act": "toggle-assignee", "data-id": person.id, disabled: !edit }, avatar(person), person.display_name);
          })),
        ),
        el("div", { class: "prop" },
          el("span", { class: "prop-k", text: "封面" }),
          el("div", { class: "swatches" }, el("button", { type: "button", class: card.cover_color ? "swatch" : "swatch is-on", "data-act": "cover", "data-color": "", text: "无", disabled: !edit }), ...COLORS.map((color) => {
            const button = el("button", { type: "button", class: card.cover_color === color ? "swatch is-on" : "swatch", "data-act": "cover", "data-color": color, disabled: !edit, "aria-label": color });
            button.style.background = color;
            return button;
          })),
        ),
      ),
      el("div", { class: "section" }, el("h3", { text: "描述" }), edit ? el("textarea", { class: "desc-input", "data-save": "description", text: card.description || "", "aria-label": "描述" }) : markdown(card.description || "没有描述")),
      el("div", { class: "section" }, el("h3", { text: "标签" }), el("div", { class: "pills" }, ...labels.map((label) => {
        const on = card.label_ids.includes(label.id);
        const button = el("button", { type: "button", class: on ? "pill is-on" : "pill", "data-act": "toggle-label", "data-id": label.id, disabled: !edit, text: label.name });
        button.style.setProperty("--c", safeColor(label.color));
        return button;
      })), edit ? el("form", { "data-form": "label", class: "composer" }, el("input", { name: "name", placeholder: "新标签", required: true }), el("button", { class: "btn-tiny", text: "添加" })) : null),
      el("div", { class: "section" }, el("h3", { text: "清单" }), ...data.checklists.map(checklistBlock), edit ? el("form", { "data-form": "checklist", class: "composer" }, el("input", { name: "title", placeholder: "清单标题", required: true }), el("button", { class: "btn-tiny", text: "添加" })) : null),
      el("div", { class: "section" }, el("h3", { text: "附件" }), ...data.attachments.map(fileRow), edit ? el("input", { class: "file-input", type: "file", "data-act": "upload" }) : null),
      el("div", { class: "section" },
        el("h3", { text: "评论" }),
        ...data.comments.map((comment) => el("article", { class: "comment" },
          el("header", {}, comment.user ? avatar(comment.user) : null, el("strong", { text: comment.user?.display_name || "成员" }), el("span", { class: "muted", text: relative(comment.created_at) + (comment.edited ? " · 已编辑" : "") }), comment.mine ? el("button", { type: "button", class: "icon-btn icon-btn-sm check-remove", "data-act": "delete-comment", "data-id": comment.id, "aria-label": "删除评论" }, glyph("trash")) : null),
          el("p", { text: comment.body }),
        )),
        edit ? el("form", { "data-form": "comment", class: "comment-form" }, el("textarea", { name: "body", placeholder: "写评论，用 @显示名 提及成员", required: true }), el("button", { class: "btn-primary btn-tiny", text: "发送" })) : null,
      ),
      el("div", { class: "section" }, el("h3", { text: "动态" }), activityList(data.activity)),
      edit ? el("div", { class: "more-actions" },
        el("button", { class: "btn-ghost", "data-act": "duplicate", text: "复制" }),
        el("button", { class: "btn-ghost", "data-act": card.archived ? "restore-card" : "archive-card", text: card.archived ? "恢复" : "归档" }),
        el("button", { class: "btn-danger", "data-act": "delete-card", text: "删除" }),
      ) : null,
    ),
  );
  const panel = drawer.querySelector(".drawer-panel");
  if (panel) panel.scrollTop = scroll;
}

function columnName(id) {
  return state.board?.columns.find((column) => column.id === id)?.name || "";
}

function checklistBlock(list) {
  const done = list.items.filter((item) => item.done).length;
  const edit = state.detail.card.can_edit;
  return el("div", { class: "checklist" },
    el("div", { class: "checklist-head" }, el("strong", { text: list.title }), el("span", { class: "count", text: `${done}/${list.items.length}` })),
    ...list.items.map((item) => el("div", { class: "check-item" },
      el("label", { class: "check" }, el("input", { type: "checkbox", "data-act": "item", "data-id": item.id, checked: item.done, disabled: !edit }), el("span", { text: item.text })),
      edit ? el("button", { type: "button", class: "icon-btn icon-btn-sm check-remove", "data-act": "delete-item", "data-id": item.id, "aria-label": "删除清单项" }, glyph("trash")) : null,
    )),
    edit ? el("form", { "data-form": "item", class: "composer" }, el("input", { type: "hidden", name: "checklist_id", value: list.id }), el("input", { name: "text", placeholder: "清单项", required: true }), el("button", { class: "btn-tiny", text: "添加" })) : null,
  );
}

function fileRow(file) {
  const row = el("div", { class: "attach" });
  if (file.image) row.append(el("img", { src: `/api/attachments/${file.id}/file`, alt: "" }));
  row.append(el("div", { class: "attach-meta" }, el("a", { href: `/api/attachments/${file.id}/file`, text: file.filename }), el("span", { class: "muted", text: fileSize(file.size) })));
  if (state.detail.card.can_edit) row.append(el("button", { type: "button", class: "icon-btn icon-btn-sm check-remove", "data-act": "delete-file", "data-id": file.id, "aria-label": "删除附件" }, glyph("trash")));
  return row;
}

function paintModal() {
  if (!state.modal) {
    modal.hidden = true;
    modal.replaceChildren();
    return;
  }
  modal.hidden = false;
  const kind = state.modal.type;
  const card = el("form", { class: "modal-card", "data-form": kind });
  card.append(el("div", { class: "split" }, el("h2", { text: state.modal.title }), el("button", { type: "button", class: "icon-btn", "data-act": "close-modal", "aria-label": "关闭" }, glyph("close"))));
  if (kind === "project" || kind === "column") {
    card.append(el("label", { class: "field" }, "名称", el("input", { name: "name", value: state.modal.name || "", required: true, "data-autofocus": "1" })));
    if (kind === "project") card.append(el("label", { class: "field" }, "简介", el("textarea", { name: "description" })));
    if (kind === "column") card.append(el("label", { class: "field" }, "在制品上限，可留空", el("input", { name: "wip_limit", type: "number", min: "1", max: "99", value: state.modal.wip || "" })));
    card.append(el("div", { class: "field" }, "颜色", colorPicker(state.modal.color || COLORS[0])));
  }
  if (kind === "confirm") card.append(el("p", { text: state.modal.body }));
  card.append(el("div", { class: "modal-foot" },
    el("button", { type: "button", class: "btn-ghost", "data-act": "close-modal", text: "取消" }),
    el("button", { type: "submit", class: kind === "confirm" ? "btn-danger" : "btn-primary", text: state.modal.ok || "确定" }),
  ));
  if (state.modal.remove) card.append(el("div", { class: "modal-extra" }, el("button", { type: "button", class: "btn-danger btn-tiny", "data-act": "delete-column", "data-id": state.modal.id, text: "删除列表" })));
  modal.replaceChildren(el("button", { class: "modal-backdrop", "data-act": "close-modal", "aria-label": "关闭" }), card);
}

function paintBadges() {
  document.querySelectorAll("[data-badge]").forEach((node) => {
    node.textContent = state.unread ? String(state.unread) : "";
  });
}

function formData(form) {
  return Object.fromEntries(new FormData(form).entries());
}

async function run(node, fn) {
  if (node) node.disabled = true;
  try {
    await fn();
  } catch (error) {
    toast(error.message || "请求失败");
    if (error.status === 401) {
      state.user = null;
      render();
    }
  } finally {
    if (node) node.disabled = false;
  }
}

function idOf(node) {
  return Number(node.dataset.id);
}

const clicks = {
  "auth-mode"(node) {
    state.authMode = node.dataset.mode;
    render();
  },
  "send-code"(node) {
    const email = node.closest("form")?.email?.value?.trim() || "";
    if (!email) {
      toast("请先填写邮箱");
      return;
    }
    node.disabled = true;
    api("/api/auth/code", { method: "POST", body: { email } }).then((data) => {
      toast("验证码已发送");
      startCodeWait(data.retry_after || 60);
    }).catch((error) => {
      toast(error.message || "请求失败");
      node.disabled = state.codeWait > 0;
    });
  },
  nav(node) {
    state.sidebar = false;
    if (node.dataset.view === "board") {
      if (state.projectId) go(`#/board/${state.projectId}`);
      else go("#/projects");
    } else go(`#/${node.dataset.view}`);
  },
  "toggle-side"() {
    state.sidebar = !state.sidebar;
    render();
  },
  "close-side"() {
    state.sidebar = false;
    render();
  },
  "open-project"(node) {
    go(`#/board/${idOf(node)}`);
  },
  "open-settings"(node) {
    go(`#/settings/${idOf(node) || state.projectId}`);
  },
  "new-project"() {
    state.modal = { type: "project", title: "新建项目", ok: "创建" };
    paintModal();
  },
  "close-modal"() {
    state.modal = null;
    paintModal();
  },
  "close-drawer"() {
    closeDrawer();
  },
  "toggle-archived"(node) {
    state.showArchived = !state.showArchived;
    run(node, async () => { await loadProjects(); render(); });
  },
  filter(node) {
    state.filters[node.dataset.key] = !state.filters[node.dataset.key];
    render();
  },
  "filter-select"(node, event) {
    toggleFilterPop(node);
  },
  "filter-pick"(node) {
    const trigger = node.closest(".filter-trigger");
    if (!trigger) return;
    const key = trigger.id === "filter-label" ? "label" : "priority";
    state.filters[key] = node.dataset.value || "";
    closeFilterPops();
    paintCanvas();
    paintFilterLock();
  },

  compose(node) {
    state.compose = { columnId: Number(node.dataset.column) };
    paintCanvas();
    document.querySelector("[data-autofocus]")?.focus();
  },
  "new-column"() {
    state.modal = { type: "column", title: "新列表", ok: "添加" };
    paintModal();
  },
  "edit-column"(node) {
    const id = idOf(node);
    const column = state.board.columns.find((item) => item.id === id);
    state.modal = { type: "column", title: "列表设置", id, name: column.name, color: column.color, wip: column.wip_limit || "", ok: "保存", remove: true };
    paintModal();
  },
  "delete-column"(node) {
    const id = idOf(node);
    run(node, async () => {
      await api(`/api/columns/${id}`, { method: "DELETE" });
      state.modal = null;
      await reloadBoard();
      render();
    });
  },
  "pick-color"(node) {
    state.color = node.dataset.color;
    node.parentElement.querySelectorAll(".swatch").forEach((swatch) => swatch.classList.toggle("is-on", swatch === node));
  },
  priority(node) {
    run(node, () => saveCard({ priority: node.dataset.value }));
  },
  cover(node) {
    run(node, () => saveCard({ cover_color: node.dataset.color || null }));
  },
  done(node) {
    run(node, () => saveCard({ done: node.checked }));
  },
  "toggle-label"(node) {
    run(node, () => toggleIds("labels", idOf(node)));
  },
  "toggle-assignee"(node) {
    run(node, () => toggleIds("assignees", idOf(node)));
  },
  accept(node) {
    const id = idOf(node);
    run(node, async () => { await api(`/api/notifications/${id}/accept`, { method: "POST" }); toast("已加入项目"); await openNotes(); });
  },
  reject(node) {
    run(node, async () => { await api(`/api/notifications/${idOf(node)}/reject`, { method: "POST" }); await openNotes(); });
  },
  "read-all"(node) {
    run(node, async () => { await api("/api/notifications/read-all", { method: "POST" }); await openNotes(); });
  },
  "open-task"(node) {
    state.pendingCard = idOf(node);
    go(`#/board/${node.dataset.project}`);
  },
  logout(node) {
    run(node, async () => { await api("/api/auth/logout", { method: "POST" }); state.user = null; render(); });
  },
  "cancel-invite"(node) {
    const id = idOf(node);
    run(node, async () => { state.settings = await api(`/api/projects/${state.projectId}/invites/${id}/cancel`, { method: "POST" }); render(); });
  },
  leave(node) {
    run(node, async () => { await api(`/api/projects/${state.projectId}/leave`, { method: "POST" }); go("#/projects"); });
  },
  "archive-project"(node) {
    run(node, async () => { await api(`/api/projects/${state.projectId}/archive`, { method: "POST" }); go("#/projects"); });
  },
  "restore-project"(node) {
    run(node, async () => { await api(`/api/projects/${state.projectId}/restore`, { method: "POST" }); await openSettings(state.projectId); });
  },
  "delete-project"() {
    state.modal = { type: "confirm", title: "删除项目", body: "卡片、评论和附件会一起删除。今天的创建次数不会退回。", ok: "删除", action: "delete-project" };
    paintModal();
  },
  transfer(node) {
    const id = idOf(node);
    run(node, async () => { state.settings = await api(`/api/projects/${state.projectId}/transfer`, { method: "POST", body: { user_id: id } }); render(); });
  },
  "remove-member"(node) {
    const id = idOf(node);
    run(node, async () => { state.settings = await api(`/api/projects/${state.projectId}/members/${id}`, { method: "DELETE" }); render(); });
  },
  duplicate(node) {
    run(node, async () => { await api(`/api/cards/${state.cardId}/duplicate`, { method: "POST" }); await reloadBoard(); toast("已复制"); });
  },
  "archive-card"(node) {
    run(node, async () => { await api(`/api/cards/${state.cardId}/archive`, { method: "POST" }); closeDrawer(); await reloadBoard(); });
  },
  "restore-card"(node) {
    run(node, async () => { await api(`/api/cards/${state.cardId}/restore`, { method: "POST" }); await openCard(state.cardId); await reloadBoard(); });
  },
  "delete-card"() {
    state.modal = { type: "confirm", title: "删除卡片", body: "这张卡片和它的评论、附件会被删除。", ok: "删除", action: "delete-card" };
    paintModal();
  },
  "delete-comment"(node) {
    const id = idOf(node);
    run(node, async () => { await api(`/api/comments/${id}`, { method: "DELETE" }); await openCard(state.cardId); });
  },
  "delete-item"(node) {
    const id = idOf(node);
    run(node, async () => { await api(`/api/checklist-items/${id}`, { method: "DELETE" }); await openCard(state.cardId); });
  },
  "delete-file"(node) {
    const id = idOf(node);
    run(node, async () => { await api(`/api/attachments/${id}`, { method: "DELETE" }); await openCard(state.cardId); await reloadBoard(); });
  },
  item(node) {
    const id = idOf(node);
    run(node, async () => { await api(`/api/checklist-items/${id}`, { method: "PATCH", body: { done: node.checked } }); await openCard(state.cardId); await reloadBoard(); });
  },
};

document.addEventListener("click", (event) => {
  const node = event.target.closest("[data-act]");
  clicks[node?.dataset.act]?.(node);
});

function columnBody(data) {
  return { name: data.name, color: state.color, wip_limit: data.wip_limit ? Number(data.wip_limit) : null };
}

const forms = {
  async auth(data) {
    const path = state.authMode === "login" ? "/api/auth/login" : "/api/auth/register";
    await api(path, { method: "POST", body: data });
    applyBootstrap(await api("/api/bootstrap"));
    go("#/projects");
  },
  async project(data) {
    if (!state.modal) return;
    const created = await api("/api/projects", { method: "POST", body: { name: data.name, description: data.description || "", color: state.color } });
    state.quota = created.quota;
    state.modal = null;
    go(`#/board/${created.project.id}`);
  },
  async "project-save"(data) {
    state.settings = await api(`/api/projects/${state.projectId}`, { method: "PATCH", body: { name: data.name, description: data.description || "", color: state.color } });
    toast("已保存");
    render();
  },
  async column(data) {
    const body = columnBody(data);
    if (state.modal?.id) await api(`/api/columns/${state.modal.id}`, { method: "PATCH", body });
    else await api(`/api/projects/${state.projectId}/columns`, { method: "POST", body });
    state.modal = null;
    await reloadBoard();
    render();
  },
  async confirm() {
    if (state.modal?.action === "delete-project") {
      await api(`/api/projects/${state.projectId}`, { method: "DELETE" });
      state.modal = null;
      go("#/projects");
    } else if (state.modal?.action === "delete-card") {
      await api(`/api/cards/${state.cardId}`, { method: "DELETE" });
      state.modal = null;
      closeDrawer();
      await reloadBoard();
      render();
    }
  },
  async card(data) {
    await api(`/api/projects/${state.projectId}/cards`, { method: "POST", body: { column_id: Number(data.column_id), title: data.title } });
    state.compose = null;
    await reloadBoard();
  },
  async invite(data) {
    state.settings = await api(`/api/projects/${state.projectId}/invites`, { method: "POST", body: data });
    toast("已发送站内邀请");
    render();
  },
  async account(data) {
    state.user = await api("/api/auth/me", { method: "PATCH", body: { display_name: data.display_name, avatar_color: state.color } });
    toast("已保存");
    render();
  },
  async password(data, form) {
    await api("/api/auth/password", { method: "POST", body: data });
    form.reset();
    toast("密码已更新");
  },
  async comment(data) {
    state.detail = await api(`/api/cards/${state.cardId}/comments`, { method: "POST", body: { body: data.body } });
    paintDrawer();
    await reloadBoard();
  },
  async checklist(data) {
    await api(`/api/cards/${state.cardId}/checklists`, { method: "POST", body: { title: data.title } });
    await openCard(state.cardId);
    await reloadBoard();
  },
  async item(data) {
    await api(`/api/checklists/${data.checklist_id}/items`, { method: "POST", body: { text: data.text } });
    await openCard(state.cardId);
    await reloadBoard();
  },
  async label(data) {
    await api(`/api/projects/${state.projectId}/labels`, { method: "POST", body: { name: data.name, color: state.color } });
    await reloadBoard();
    await openCard(state.cardId);
  },
};

document.addEventListener("submit", (event) => {
  const form = event.target.closest("[data-form]");
  if (!form) return;
  event.preventDefault();
  const data = formData(form);
  run(form.querySelector("[type=submit]"), () => forms[form.dataset.form]?.(data, form));
});

document.addEventListener("change", (event) => {
  const node = event.target;
  if (node.dataset.act === "role") {
    run(node, async () => {
      state.settings = await api(`/api/projects/${state.projectId}/members/${node.dataset.id}`, { method: "PATCH", body: { role: node.value } });
      render();
    });
  } else if (node.dataset.act === "upload" && node.files?.[0]) {
    const body = new FormData();
    body.append("file", node.files[0]);
    run(node, async () => {
      await api(`/api/cards/${state.cardId}/attachments`, { method: "POST", body });
      await openCard(state.cardId);
      await reloadBoard();
    });
  }
});

document.addEventListener("input", (event) => {
  if (event.target.id === "board-search") {
    state.filters.q = event.target.value;
    paintCanvas();
    paintFilterLock();
  }
});

document.addEventListener("focusout", (event) => {
  const node = event.target;
  if (!node.dataset?.save || !state.cardId) return;
  const card = state.detail?.card;
  if (!card) return;
  if (node.dataset.save === "title" && node.value.trim() && node.value.trim() !== card.title) run(null, () => saveCard({ title: node.value.trim() }));
  if (node.dataset.save === "description" && node.value !== (card.description || "")) run(null, () => saveCard({ description: node.value }));
  if (node.dataset.save === "due" && (node.value || null) !== (card.due_on || null)) run(null, () => saveCard({ due_on: node.value || null }));
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (document.querySelector(".filter-trigger.is-open")) { closeFilterPops(); return; }
  if (state.modal) {
    state.modal = null;
    paintModal();
  } else if (state.cardId) closeDrawer();
  else if (state.sidebar) {
    state.sidebar = false;
    render();
  }
});

async function saveCard(body) {
  state.detail = await api(`/api/cards/${state.cardId}`, { method: "PATCH", body });
  syncFace();
  paintDrawer();
  paintCanvas();
}

function syncFace() {
  const card = findCard(state.cardId);
  const next = state.detail?.card;
  if (!card || !next) return;
  Object.assign(card, next);
}

async function toggleIds(kind, id) {
  const key = kind === "labels" ? "label_ids" : "assignee_ids";
  const ids = new Set(state.detail.card[key]);
  if (ids.has(id)) ids.delete(id);
  else ids.add(id);
  state.detail = await api(`/api/cards/${state.cardId}/${kind}`, { method: "PUT", body: { ids: [...ids] } });
  syncFace();
  paintDrawer();
  paintCanvas();
}

async function reloadBoard() {
  if (!state.projectId) return;
  state.board = await api(`/api/projects/${state.projectId}/board`);
  paintCanvas();
}

installDrag({
  canDrag: () => editable() && !filtersOn() && !state.board.project.archived,
  onDragChange: (dragging) => { state.dragging = dragging; },
  onTap: (kind, id) => { if (kind === "card") openCard(id); },
  onDrop: (detail) => run(null, async () => {
    if (detail.kind === "card" && detail.columnId) {
      const result = await api(`/api/cards/${detail.id}/move`, { method: "POST", body: { column_id: detail.columnId, index: detail.index } });
      const pool = new Map();
      for (const column of state.board.columns) {
        for (const card of column.cards) pool.set(card.id, card);
      }
      for (const update of result.columns) {
        const column = state.board.columns.find((item) => item.id === update.id);
        if (!column) continue;
        const archived = column.cards.filter((card) => card.archived && !update.card_ids.includes(card.id));
        column.cards = update.card_ids.map((cardId) => pool.get(cardId)).filter(Boolean);
        for (const card of column.cards) card.column_id = column.id;
        column.cards.push(...archived);
      }
      paintCanvas();
    } else if (detail.kind === "column") {
      const ids = state.board.columns.map((column) => column.id);
      const [picked] = ids.splice(ids.indexOf(detail.id), 1);
      ids.splice(detail.index, 0, picked);
      await api(`/api/projects/${state.projectId}/columns/reorder`, { method: "POST", body: { ids } });
      state.board.columns.sort((a, b) => ids.indexOf(a.id) - ids.indexOf(b.id));
      render();
    }
  }),
});
