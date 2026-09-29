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
  color: COLORS[0],
};

const app = document.getElementById("app");
const drawer = document.getElementById("drawer");
const modal = document.getElementById("modal");
const toasts = document.getElementById("toasts");

function toast(message) {
  const node = el("div", { class: "toast", text: message });
  toasts.append(node);
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

async function boot() {
  try {
    const data = await api("/api/bootstrap");
    applyBootstrap(data);
  } catch {
    state.user = null;
  }
  route();
  setInterval(poll, 8000);
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

async function route() {
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
  await loadProjects();
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
  render();
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
  app.replaceChildren(state.user ? shell() : authView());
  paintBadges();
  if (state.cardId) paintDrawer();
  else drawer.hidden = true;
  paintModal();
  document.querySelector("[data-autofocus]")?.focus();
}

function authView() {
  const login = state.authMode === "login";
  return el("div", { class: "auth" },
    el("section", { class: "auth-hero" },
      el("div", { class: "brand" }, mark(), "看板"),
      el("div", { class: "hero-copy" },
        el("h1", { text: "把事情，排成看得见的秩序。" }),
        el("p", { text: "只用邮箱注册。邀请同伴进项目，对方在站内批准后，一起推进。" }),
        el("div", { class: "hero-board" }, mini("待办", 2), mini("进行中", 1), mini("完成", 1, true)),
      ),
    ),
    el("section", { class: "auth-panel" },
      el("form", { class: "auth-card", "data-form": "auth" },
        el("div", { class: "brand" }, mark(), "看板"),
        el("h2", { text: login ? "欢迎回来" : "创建账号" }),
        el("p", { class: "lede", text: "没有手机号，没有第三方登录。邮箱就是账号。" }),
        el("div", { class: "seg" },
          el("button", { type: "button", class: login ? "is-on" : "", "data-act": "auth-mode", "data-mode": "login", text: "登录" }),
          el("button", { type: "button", class: login ? "" : "is-on", "data-act": "auth-mode", "data-mode": "register", text: "注册" }),
        ),
        field("邮箱", "email", "email", "you@example.com"),
        login ? null : field("显示名", "display_name", "text", "怎么称呼你"),
        field("密码", "password", "password", login ? "你的密码" : "至少 8 位"),
        el("button", { class: "btn-primary btn-block", type: "submit", text: login ? "进入看板" : "用邮箱注册" }),
      ),
    ),
  );
}

function mark() {
  return el("span", { class: "mark", "aria-hidden": "true" }, el("i"), el("i"), el("i"));
}

function mini(title, count, rose = false) {
  const col = el("div", { class: "mini-col" }, el("b", { text: title }));
  for (let i = 0; i < count; i += 1) col.append(el("div", { class: rose && i === 0 ? "mini-card short" : "mini-card" }));
  return col;
}

function field(label, name, type, placeholder) {
  return el("label", { class: "field" }, label, el("input", { name, type, placeholder, required: true, autocomplete: name === "password" ? "current-password" : "email" }));
}

function shell() {
  return el("div", { class: "shell" },
    el("aside", { class: state.sidebar ? "sidebar is-open" : "sidebar" },
      el("div", { class: "brand" }, mark(), "看板"),
      el("nav", { class: "side-nav" },
        nav("projects", "项目", "board"),
        nav("tasks", "我的任务", "tasks"),
        nav("notifications", "通知", "bell", state.unread > 0),
      ),
      el("div", { class: "side-label", text: "最近" }),
      el("div", { class: "side-projects" }, ...state.projects.slice(0, 12).map((project) => {
        const link = el("button", { class: project.id === state.projectId ? "project-link is-on" : "project-link", "data-act": "open-project", "data-id": project.id });
        const dot = el("i", { class: "dot" });
        dot.style.setProperty("--c", safeColor(project.color));
        link.append(dot, el("span", { text: project.name }));
        return link;
      })),
      el("button", { class: "user-chip", "data-act": "nav", "data-view": "account" }, avatar(state.user, "lg"), el("span", {}, el("strong", { text: state.user.display_name }), el("small", { text: state.user.email }))),
    ),
    state.sidebar ? el("button", { class: "backdrop", "data-act": "close-side", "aria-label": "关闭菜单" }) : null,
    el("div", { class: "main" },
      el("header", { class: "topbar" },
        el("button", { class: "icon-btn menu-btn", "data-act": "toggle-side", "aria-label": "菜单" }, glyph("menu")),

        el("span", { class: "spacer" }),
        el("button", { class: "icon-btn", "data-act": "nav", "data-view": "notifications", "aria-label": "通知" }, glyph("bell"), state.unread ? el("i", { class: "dot" }) : null),
      ),
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
  if (view === "notifications" && state.unread) button.append(el("i", { class: "badge", text: String(state.unread) }));
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
      el("div", { class: "row" },
        el("button", { class: "btn-ghost", "data-act": "toggle-archived", text: state.showArchived ? "返回项目" : "已归档" }),
        el("button", { class: "btn-primary", "data-act": "new-project", disabled: state.quota.remaining <= 0 }, glyph("plus"), el("span", { text: "新建" })),
      ),
    ),
    list.length ? el("div", { class: "project-grid" }, ...list.map(projectCard)) : el("div", { class: "empty" }, el("strong", { text: "还没有项目" }), "建一个，从第一张卡片开始。"),
  );
}

function projectCard(project) {
  const card = el("button", { class: "project-card", "data-act": "open-project", "data-id": project.id });
  card.style.setProperty("--c", safeColor(project.color));
  card.append(
    el("strong", { text: project.name }),
    el("p", { text: project.description || "没有简介" }),
    el("div", { class: "meta" }, `${project.open_cards} 张卡片`, "·", `${project.member_count} 人`, "·", ROLES[project.role] || ""),
  );
  return card;
}

function boardView() {
  if (!state.board) return el("div", { class: "empty" }, el("strong", { text: "选择一个项目" }));
  const project = state.board.project;
  return el("section", { class: "board-page" },
    el("div", { class: "board-head" },
      el("div", {}, el("h2", { text: project.name }), el("p", { class: "muted", text: project.description || "把卡片拖到它该在的位置。" })),
      el("div", { class: "row" },
        el("div", { class: "faces" }, ...state.board.members.slice(0, 5).map((person) => avatar(person))),
        el("button", { class: "btn-ghost", "data-act": "open-settings", "data-id": project.id, text: "成员" }),
      ),
    ),
    el("div", { class: "filters" },
      el("input", { class: "search", id: "board-search", placeholder: "搜索卡片", value: state.filters.q }),
      chip("mine", "我的"),
      chip("overdue", "逾期"),
      chip("hideDone", "隐藏完成"),
      chip("archived", "归档"),
      el("select", { id: "filter-label", "aria-label": "标签" }, el("option", { value: "", text: "全部标签" }), ...state.board.labels.map((label) => el("option", { value: label.id, text: label.name, selected: String(state.filters.label) === String(label.id) }))),
      el("select", { id: "filter-priority", "aria-label": "优先级" }, ...PRIORITIES.map(([value, label]) => el("option", { value: value === "none" ? "" : value, text: value === "none" ? "全部优先级" : label, selected: state.filters.priority === value }))),
    ),
    filtersOn() ? el("p", { class: "muted", text: "筛选开启时不能拖动，避免放错位置。" }) : null,
    canvasNode(),
  );
}

function chip(key, label) {
  return el("button", { class: state.filters[key] ? "chip is-on" : "chip", "data-act": "filter", "data-key": key, text: label });
}

function canvasNode() {
  const node = el("div", { class: "board-canvas", id: "board-canvas" });
  for (const column of state.board.columns) node.append(columnNode(column));
  if (editable()) node.append(el("button", { class: "btn-ghost add-column", "data-act": "new-column" }, glyph("plus"), el("span", { text: "添加列表" })));
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
  const head = el("div", { class: "column-head" },
    editable() ? el("button", { class: "grip", "data-drag": "column", "data-id": column.id, "aria-label": "拖动列表" }, glyph("grip")) : null,
    el("strong", { text: column.name }),
    el("span", { class: column.wip_limit && live.length > column.wip_limit ? "wip is-over" : "count", text: column.wip_limit ? `${live.length}/${column.wip_limit}` : String(live.length) }),
    el("span", { class: "spacer" }),
    editable() ? el("button", { class: "icon-btn", "data-act": "edit-column", "data-id": column.id, "aria-label": "列表设置" }, glyph("settings")) : null,
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
    } else node.append(el("button", { class: "btn-tiny", "data-act": "compose", "data-column": column.id, text: "添加卡片" }));
  }
  return node;
}

function cardNode(card, column) {
  const due = dueInfo(card.due_on);
  const node = el("article", { class: `card${card.done ? " is-done" : ""}${card.archived ? " is-archived" : ""}`, "data-drag": "card", "data-id": card.id, "data-column": column.id });
  node.style.setProperty("--c", safeColor(card.cover_color || priorityColor(card.priority), "transparent"));
  const labels = state.board.labels.filter((label) => card.label_ids.includes(label.id));
  node.append(el("h3", { class: "card-title", text: card.title }));
  if (labels.length) node.append(el("div", { class: "pills" }, ...labels.map((label) => {
    const pill = el("span", { class: "pill", text: label.name });
    pill.style.background = safeColor(label.color);
    return pill;
  })));
  const foot = el("div", { class: "card-foot" });
  if (due) foot.append(el("span", { class: due.over || due.today ? "due is-over" : "due", text: due.text }));
  if (card.checklist.total) foot.append(el("span", { text: `${card.checklist.done}/${card.checklist.total}` }));
  if (card.comment_count) foot.append(el("span", { text: `${card.comment_count} 评` }));
  const people = state.board.members.filter((person) => card.assignee_ids.includes(person.id));
  foot.append(el("span", { class: "spacer" }), ...people.slice(0, 3).map((person) => avatar(person)));
  node.append(foot);
  return node;
}

function priorityColor(priority) {
  return { low: "#3D6B8A", medium: "#C47B2B", high: "#D63A56", urgent: "#8A4B5A" }[priority] || "transparent";
}

function tasksView() {
  const groups = [
    ["逾期", state.tasks.filter((card) => dueInfo(card.due_on)?.over && !card.done)],
    ["今天", state.tasks.filter((card) => dueInfo(card.due_on)?.today && !card.done)],
    ["之后", state.tasks.filter((card) => !dueInfo(card.due_on)?.over && !dueInfo(card.due_on)?.today)],
  ];
  return el("section", {},
    el("div", { class: "page-head" }, el("div", {}, el("h2", { text: "我的任务" }), el("p", { text: "指派给你、尚未归档的卡片。" }))),
    ...groups.map(([title, cards]) => el("div", { class: "section" }, el("h3", { text: title }), cards.length ? el("div", {}, ...cards.map(taskRow)) : el("p", { class: "muted", text: "没有" }))),
  );
}

function taskRow(card) {
  const due = dueInfo(card.due_on);
  return el("button", { class: "task list-row", "data-act": "open-task", "data-id": card.id, "data-project": card.project_id },
    el("i", { class: "dot", style: `--c:${safeColor(card.project_color)}` }),
    el("strong", { text: card.title }),
    el("span", { class: "muted", text: `${card.project_name} · ${card.column_name}` }),
    due ? el("span", { class: due.over ? "due is-over" : "muted", text: due.text }) : null,
  );
}

function notesView() {
  return el("section", {},
    el("div", { class: "page-head" },
      el("div", {}, el("h2", { text: "通知" }), el("p", { text: "邀请需要你批准后才会加入项目。" })),
      el("button", { class: "btn-ghost", "data-act": "read-all", text: "全部已读" }),
    ),
    state.notes.length ? el("div", {}, ...state.notes.map(noteRow)) : el("div", { class: "empty" }, el("strong", { text: "没有新消息" })),
  );
}

function noteRow(note) {
  const pending = note.type === "project_invite" && note.status === "pending";
  return el("article", { class: "note" },
    el("header", {}, note.actor ? avatar(note.actor) : glyph("bell"), el("strong", { text: note.title }), el("span", { class: "muted", text: relative(note.created_at) })),
    el("p", { text: note.body }),
    pending ? el("div", { class: "row" },
      el("button", { class: "btn-primary btn-tiny", "data-act": "accept", "data-id": note.id, text: "批准" }),
      el("button", { class: "btn-ghost btn-tiny", "data-act": "reject", "data-id": note.id, text: "拒绝" }),
    ) : el("span", { class: "muted", text: { accepted: "已接受", rejected: "已拒绝", cancelled: "已撤回", info: "" }[note.status] || "" }),
  );
}

function settingsView() {
  const data = state.settings;
  if (!data) return el("p", { text: "加载中" });
  const admin = canAdmin(data.role);
  const owner = data.role === "owner";
  return el("section", { class: "settings-grid" },
    el("div", {},
      el("h2", { text: data.project.name }),
      admin ? el("form", { "data-form": "project-save" },
        el("label", { class: "field" }, "名称", el("input", { name: "name", value: data.project.name, required: true })),
        el("label", { class: "field" }, "简介", el("textarea", { name: "description", text: data.project.description })),
        colorPicker(data.project.color),
        el("button", { class: "btn-primary", text: "保存项目" }),
      ) : el("p", { text: data.project.description || "没有简介" }),
      el("div", { class: "section" }, el("h3", { text: "成员" }), ...data.members.map((person) => memberRow(person, data))),
      admin ? el("form", { class: "section", "data-form": "invite" },
        el("h3", { text: "邀请" }),
        el("label", { class: "field" }, "对方邮箱", el("input", { name: "email", type: "email", placeholder: "已注册的邮箱", required: true })),
        el("label", { class: "field" }, "角色", el("select", { name: "role" }, el("option", { value: "member", text: "成员" }), el("option", { value: "admin", text: "管理员" }), el("option", { value: "viewer", text: "只读" }))),
        el("button", { class: "btn-primary", text: "发送站内邀请" }),
      ) : null,
      data.invites?.length ? el("div", { class: "section" }, el("h3", { text: "等待批准" }), ...data.invites.map((invite) => el("div", { class: "list-row row" }, el("span", { text: `${invite.display_name} · ${invite.email}` }), el("button", { class: "btn-tiny", "data-act": "cancel-invite", "data-id": invite.id, text: "撤回" })))) : null,
      el("div", { class: "danger-zone" },
        owner ? null : el("button", { class: "btn-ghost", "data-act": "leave", text: "退出项目" }),
        admin ? el("button", { class: "btn-ghost", "data-act": data.project.archived ? "restore-project" : "archive-project", text: data.project.archived ? "恢复项目" : "归档项目" }) : null,
        owner ? el("button", { class: "btn-danger", "data-act": "delete-project", text: "删除项目" }) : null,
      ),
    ),
    el("div", {},
      el("h3", { text: "动态" }),
      ...state.activity.slice(0, 30).map((item) => el("div", { class: "list-row" }, el("strong", { text: item.user?.display_name || "有人" }), " ", ACTIONS[item.action] || item.action, item.detail?.title ? `「${item.detail.title}」` : "", el("div", { class: "muted", text: relative(item.created_at) }))),
    ),
  );
}

function memberRow(person, data) {
  const admin = canAdmin(data.role);
  return el("div", { class: "member-row row" },
    avatar(person),
    el("div", {}, el("strong", { text: person.display_name }), el("div", { class: "muted", text: person.email })),
    el("span", { class: "spacer" }),
    person.role === "owner" ? el("span", { text: "拥有者" }) : admin && person.id !== state.user.id ? el("select", { "data-act": "role", "data-id": person.id }, ...["admin", "member", "viewer"].map((role) => el("option", { value: role, text: ROLES[role], selected: person.role === role }))) : el("span", { text: ROLES[person.role] }),
    data.role === "owner" && person.id !== state.user.id ? el("button", { class: "btn-tiny", "data-act": "transfer", "data-id": person.id, text: "移交" }) : null,
    admin && person.role !== "owner" && person.id !== state.user.id ? el("button", { class: "btn-tiny", "data-act": "remove-member", "data-id": person.id, text: "移除" }) : null,
  );
}

function accountView() {
  return el("section", {},
    el("div", { class: "page-head" }, el("h2", { text: "账号" })),
    el("form", { "data-form": "account" },
      el("label", { class: "field" }, "显示名", el("input", { name: "display_name", value: state.user.display_name, required: true })),
      el("div", { class: "field" }, "头像颜色", colorPicker(state.user.avatar_color)),
      el("button", { class: "btn-primary", text: "保存" }),
    ),
    el("form", { class: "section", "data-form": "password" },
      el("h3", { text: "修改密码" }),
      el("label", { class: "field" }, "当前密码", el("input", { name: "current_password", type: "password", required: true })),
      el("label", { class: "field" }, "新密码", el("input", { name: "new_password", type: "password", required: true, minlength: "8" })),
      el("button", { class: "btn-ghost", text: "更新密码" }),
    ),
    el("button", { class: "btn-danger section", "data-act": "logout", text: "退出登录" }),
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
  drawer.hidden = false;
  drawer.replaceChildren(
    el("button", { class: "drawer-backdrop", "data-act": "close-drawer", "aria-label": "关闭" }),
    el("article", { class: "drawer-panel" },
      el("div", { class: "drawer-top" }, el("span", { class: "muted", text: columnName(card.column_id) }), el("button", { class: "icon-btn", "data-act": "close-drawer", "aria-label": "关闭" }, glyph("close"))),
      edit ? el("input", { class: "card-title", "data-save": "title", value: card.title }) : el("h2", { text: card.title }),
      el("div", { class: "section" }, el("h3", { text: "优先级" }), el("div", { class: "prio" }, ...PRIORITIES.map(([value, label]) => el("button", { type: "button", class: card.priority === value ? "is-on" : "", "data-act": "priority", "data-value": value, disabled: !edit, text: label })))),
      el("div", { class: "row section" },
        el("label", { class: "field" }, "截止日期", el("input", { type: "date", "data-save": "due", value: card.due_on || "", disabled: !edit })),
        el("label", { class: "check" }, el("input", { type: "checkbox", "data-act": "done", checked: card.done, disabled: !edit }), "完成"),
      ),
      el("div", { class: "section" }, el("h3", { text: "封面" }), el("div", { class: "swatches" }, el("button", { class: "swatch", "data-act": "cover", "data-color": "", text: "无" }), ...COLORS.map((color) => {
        const button = el("button", { type: "button", class: card.cover_color === color ? "swatch is-on" : "swatch", "data-act": "cover", "data-color": color, disabled: !edit });
        button.style.background = color;
        return button;
      }))),
      el("div", { class: "section" }, el("h3", { text: "描述" }), edit ? el("textarea", { "data-save": "description", text: card.description || "" }) : markdown(card.description || "没有描述")),
      el("div", { class: "section" }, el("h3", { text: "标签" }), el("div", { class: "pills" }, ...state.board.labels.map((label) => {
        const on = card.label_ids.includes(label.id);
        const button = el("button", { class: "pill", "data-act": "toggle-label", "data-id": label.id, disabled: !edit, text: on ? `✓ ${label.name}` : label.name });
        button.style.background = safeColor(label.color);
        button.style.opacity = on ? "1" : ".45";
        return button;
      })), edit ? el("form", { "data-form": "label", class: "composer" }, el("input", { name: "name", placeholder: "新标签", required: true }), el("button", { class: "btn-tiny", text: "添加" })) : null),
      el("div", { class: "section" }, el("h3", { text: "指派" }), el("div", { class: "row" }, ...state.board.members.map((person) => {
        const on = card.assignee_ids.includes(person.id);
        const button = el("button", { class: "btn-tiny", "data-act": "toggle-assignee", "data-id": person.id, disabled: !edit }, avatar(person), person.display_name);
        if (on) button.style.outline = "2px solid var(--ink)";
        return button;
      }))),
      el("div", { class: "section" }, el("h3", { text: "清单" }), ...data.checklists.map(checklistBlock), edit ? el("form", { "data-form": "checklist", class: "composer" }, el("input", { name: "title", placeholder: "清单标题", required: true }), el("button", { class: "btn-tiny", text: "添加" })) : null),
      el("div", { class: "section" }, el("h3", { text: "附件" }), ...data.attachments.map(fileRow), edit ? el("input", { type: "file", "data-act": "upload" }) : null),
      el("div", { class: "section" }, el("h3", { text: "评论" }), ...data.comments.map((comment) => el("article", { class: "comment" }, el("header", {}, comment.user ? avatar(comment.user) : null, el("strong", { text: comment.user?.display_name || "成员" }), el("span", { class: "muted", text: relative(comment.created_at) + (comment.edited ? " · 已编辑" : "") })), el("p", { text: comment.body }), comment.mine ? el("button", { class: "btn-tiny", "data-act": "delete-comment", "data-id": comment.id, text: "删除" }) : null)), edit ? el("form", { "data-form": "comment" }, el("textarea", { name: "body", placeholder: "写评论，用 @显示名 提及成员", required: true }), el("button", { class: "btn-primary btn-tiny", text: "发送" })) : null),
      edit ? el("div", { class: "danger-zone" },
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
  return el("div", { class: "list-row" },
    el("strong", { text: `${list.title}  ${done}/${list.items.length}` }),
    ...list.items.map((item) => el("label", { class: "check" }, el("input", { type: "checkbox", "data-act": "item", "data-id": item.id, checked: item.done, disabled: !state.detail.card.can_edit }), item.text, state.detail.card.can_edit ? el("button", { type: "button", class: "btn-tiny", "data-act": "delete-item", "data-id": item.id, text: "删" }) : null)),
    state.detail.card.can_edit ? el("form", { "data-form": "item", class: "composer" }, el("input", { type: "hidden", name: "checklist_id", value: list.id }), el("input", { name: "text", placeholder: "清单项", required: true }), el("button", { class: "btn-tiny", text: "添加" })) : null,
  );
}

function fileRow(file) {
  const row = el("div", { class: "attach" });
  if (file.image) row.append(el("img", { src: `/api/attachments/${file.id}/file`, alt: "" }));
  row.append(el("a", { href: `/api/attachments/${file.id}/file`, text: file.filename }), el("span", { class: "muted", text: fileSize(file.size) }));
  if (state.detail.card.can_edit) row.append(el("button", { class: "btn-tiny", "data-act": "delete-file", "data-id": file.id, text: "删除" }));
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
    card.append(colorPicker(state.modal.color || COLORS[0]));
  }
  if (kind === "confirm") card.append(el("p", { text: state.modal.body }));
  card.append(el("button", { type: "submit", class: kind === "confirm" ? "btn-danger" : "btn-primary", text: state.modal.ok || "确定" }));
  if (state.modal.remove) card.append(el("button", { type: "button", class: "btn-danger", "data-act": "delete-column", "data-id": state.modal.id, text: "删除列表" }));
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

document.addEventListener("click", (event) => {
  const node = event.target.closest("[data-act]");
  if (!node) return;
  const act = node.dataset.act;
  const id = Number(node.dataset.id);
  if (act === "auth-mode") {
    state.authMode = node.dataset.mode;
    render();
  } else if (act === "nav") {
    state.sidebar = false;
    if (node.dataset.view === "board") {
      if (state.projectId) go(`#/board/${state.projectId}`);
      else go("#/projects");
    } else go(`#/${node.dataset.view}`);
  } else if (act === "toggle-side") {
    state.sidebar = !state.sidebar;
    render();
  } else if (act === "close-side") {
    state.sidebar = false;
    render();
  } else if (act === "open-project") go(`#/board/${id}`);
  else if (act === "open-settings") go(`#/settings/${id || state.projectId}`);
  else if (act === "new-project") {
    state.modal = { type: "project", title: "新建项目", ok: "创建" };
    paintModal();
  } else if (act === "close-modal") {
    state.modal = null;
    paintModal();
  } else if (act === "close-drawer") closeDrawer();
  else if (act === "toggle-archived") {
    state.showArchived = !state.showArchived;
    run(node, async () => { await loadProjects(); render(); });
  } else if (act === "filter") {
    state.filters[node.dataset.key] = !state.filters[node.dataset.key];
    render();
  } else if (act === "compose") {
    state.compose = { columnId: Number(node.dataset.column) };
    paintCanvas();
    document.querySelector("[data-autofocus]")?.focus();
  } else if (act === "new-column") {
    state.modal = { type: "column", title: "新列表", ok: "添加" };
    paintModal();
  } else if (act === "edit-column") {
    const column = state.board.columns.find((item) => item.id === id);
    state.modal = { type: "column", title: "列表设置", id, name: column.name, color: column.color, wip: column.wip_limit || "", ok: "保存", remove: true };
    paintModal();
  } else if (act === "delete-column") run(node, async () => {
    await api(`/api/columns/${id}`, { method: "DELETE" });
    state.modal = null;
    await reloadBoard();
    render();
  });
  else if (act === "pick-color") {
    state.color = node.dataset.color;
    node.parentElement.querySelectorAll(".swatch").forEach((swatch) => swatch.classList.toggle("is-on", swatch === node));
  } else if (act === "priority") run(node, () => saveCard({ priority: node.dataset.value }));
  else if (act === "cover") run(node, () => saveCard({ cover_color: node.dataset.color || null }));
  else if (act === "done") run(node, () => saveCard({ done: node.checked }));
  else if (act === "toggle-label") run(node, () => toggleIds("labels", id));
  else if (act === "toggle-assignee") run(node, () => toggleIds("assignees", id));
  else if (act === "accept") run(node, async () => { await api(`/api/notifications/${id}/accept`, { method: "POST" }); toast("已加入项目"); await openNotes(); });
  else if (act === "reject") run(node, async () => { await api(`/api/notifications/${id}/reject`, { method: "POST" }); await openNotes(); });
  else if (act === "read-all") run(node, async () => { await api("/api/notifications/read-all", { method: "POST" }); await openNotes(); });
  else if (act === "open-task") {
    state.projectId = Number(node.dataset.project);
    go(`#/board/${state.projectId}`);
    setTimeout(() => openCard(id), 400);
  } else if (act === "logout") run(node, async () => { await api("/api/auth/logout", { method: "POST" }); state.user = null; render(); });
  else if (act === "cancel-invite") run(node, async () => { state.settings = await api(`/api/projects/${state.projectId}/invites/${id}/cancel`, { method: "POST" }); render(); });
  else if (act === "leave") run(node, async () => { await api(`/api/projects/${state.projectId}/leave`, { method: "POST" }); go("#/projects"); });
  else if (act === "archive-project") run(node, async () => { await api(`/api/projects/${state.projectId}/archive`, { method: "POST" }); go("#/projects"); });
  else if (act === "restore-project") run(node, async () => { await api(`/api/projects/${state.projectId}/restore`, { method: "POST" }); await openSettings(state.projectId); });
  else if (act === "delete-project") {
    state.modal = { type: "confirm", title: "删除项目", body: "卡片、评论和附件会一起删除。今天的创建次数不会退回。", ok: "删除", action: "delete-project" };
    paintModal();
  } else if (act === "transfer") run(node, async () => { state.settings = await api(`/api/projects/${state.projectId}/transfer`, { method: "POST", body: { user_id: id } }); render(); });
  else if (act === "remove-member") run(node, async () => { state.settings = await api(`/api/projects/${state.projectId}/members/${id}`, { method: "DELETE" }); render(); });
  else if (act === "duplicate") run(node, async () => { await api(`/api/cards/${state.cardId}/duplicate`, { method: "POST" }); await reloadBoard(); toast("已复制"); });
  else if (act === "archive-card") run(node, async () => { await api(`/api/cards/${state.cardId}/archive`, { method: "POST" }); closeDrawer(); await reloadBoard(); });
  else if (act === "restore-card") run(node, async () => { await api(`/api/cards/${state.cardId}/restore`, { method: "POST" }); await openCard(state.cardId); await reloadBoard(); });
  else if (act === "delete-card") {
    state.modal = { type: "confirm", title: "删除卡片", body: "这张卡片和它的评论、附件会被删除。", ok: "删除", action: "delete-card" };
    paintModal();
  } else if (act === "delete-comment") run(node, async () => { await api(`/api/comments/${id}`, { method: "DELETE" }); await openCard(state.cardId); });
  else if (act === "delete-item") run(node, async () => { await api(`/api/checklist-items/${id}`, { method: "DELETE" }); await openCard(state.cardId); });
  else if (act === "delete-file") run(node, async () => { await api(`/api/attachments/${id}`, { method: "DELETE" }); await openCard(state.cardId); await reloadBoard(); });
  else if (act === "item") run(node, async () => { await api(`/api/checklist-items/${id}`, { method: "PATCH", body: { done: node.checked } }); await openCard(state.cardId); await reloadBoard(); });
});

document.addEventListener("submit", (event) => {
  const form = event.target.closest("[data-form]");
  if (!form) return;
  event.preventDefault();
  const kind = form.dataset.form;
  const data = formData(form);
  run(form.querySelector("[type=submit]"), async () => {
    if (kind === "auth") {
      const path = state.authMode === "login" ? "/api/auth/login" : "/api/auth/register";
      await api(path, { method: "POST", body: data });
      applyBootstrap(await api("/api/bootstrap"));
      go("#/projects");
    } else if (kind === "project" && state.modal) {
      const created = await api("/api/projects", { method: "POST", body: { name: data.name, description: data.description || "", color: state.color } });
      state.quota = created.quota;
      state.modal = null;
      go(`#/board/${created.project.id}`);
    } else if (kind === "project-save") {
      state.settings = await api(`/api/projects/${state.projectId}`, { method: "PATCH", body: { name: data.name, description: data.description || "", color: state.color } });
      toast("已保存");
      render();

    } else if (kind === "column" && state.modal?.id) {
      await api(`/api/columns/${state.modal.id}`, { method: "PATCH", body: { name: data.name, color: state.color, wip_limit: data.wip_limit ? Number(data.wip_limit) : null } });
      state.modal = null;
      await reloadBoard();
      render();
    } else if (kind === "column") {
      await api(`/api/projects/${state.projectId}/columns`, { method: "POST", body: { name: data.name, color: state.color, wip_limit: data.wip_limit ? Number(data.wip_limit) : null } });
      state.modal = null;
      await reloadBoard();
      render();
    } else if (kind === "confirm" && state.modal?.action === "delete-project") {
      await api(`/api/projects/${state.projectId}`, { method: "DELETE" });
      state.modal = null;
      go("#/projects");
    } else if (kind === "confirm" && state.modal?.action === "delete-card") {
      await api(`/api/cards/${state.cardId}`, { method: "DELETE" });
      state.modal = null;
      closeDrawer();
      await reloadBoard();
      render();
    } else if (kind === "card") {
      await api(`/api/projects/${state.projectId}/cards`, { method: "POST", body: { column_id: Number(data.column_id), title: data.title } });
      state.compose = null;
      await reloadBoard();
    } else if (kind === "invite") {
      state.settings = await api(`/api/projects/${state.projectId}/invites`, { method: "POST", body: data });
      toast("已发送站内邀请");
      render();
    } else if (kind === "account") {
      state.user = await api("/api/auth/me", { method: "PATCH", body: { display_name: data.display_name, avatar_color: state.color } });
      toast("已保存");
      render();
    } else if (kind === "password") {
      await api("/api/auth/password", { method: "POST", body: data });
      form.reset();
      toast("密码已更新");
    } else if (kind === "comment") {
      state.detail = await api(`/api/cards/${state.cardId}/comments`, { method: "POST", body: { body: data.body } });
      paintDrawer();
      await reloadBoard();
    } else if (kind === "checklist") {
      await api(`/api/cards/${state.cardId}/checklists`, { method: "POST", body: { title: data.title } });
      await openCard(state.cardId);
      await reloadBoard();
    } else if (kind === "item") {
      await api(`/api/checklists/${data.checklist_id}/items`, { method: "POST", body: { text: data.text } });
      await openCard(state.cardId);
      await reloadBoard();
    } else if (kind === "label") {
      await api(`/api/projects/${state.projectId}/labels`, { method: "POST", body: { name: data.name, color: state.color } });
      await reloadBoard();
      await openCard(state.cardId);
    }
  });
});

document.addEventListener("change", (event) => {
  const node = event.target;
  if (node.id === "filter-label") {
    state.filters.label = node.value;
    paintCanvas();
  } else if (node.id === "filter-priority") {
    state.filters.priority = node.value;
    paintCanvas();
  } else if (node.dataset.act === "role") {
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

window.addEventListener("hashchange", () => { route().catch((error) => toast(error.message)); });
boot().catch((error) => toast(error.message));
