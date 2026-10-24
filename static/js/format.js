import { avatarId, avatarPath } from "./avatars.js";

export const COLORS = ["#D63A56", "#C47B2B", "#5C6B52", "#3D6B8A", "#7A5EA8", "#C46B4A", "#2F6F6A", "#8A4B5A"];
export const PRIORITIES = [
  ["none", "无"],
  ["low", "低"],
  ["medium", "中"],
  ["high", "高"],
  ["urgent", "紧急"],
];
export const ROLES = { owner: "拥有者", admin: "管理员", member: "成员", viewer: "只读" };
export const ACTIONS = {
  "project.created": "创建了项目",
  "project.updated": "更新了项目",
  "project.archived": "归档了项目",
  "project.restored": "恢复了项目",
  "project.transferred": "移交了项目",
  "invite.sent": "发出了邀请",
  "invite.cancelled": "撤回了邀请",
  "member.joined": "加入了项目",
  "member.left": "退出了项目",
  "member.removed": "移除了成员",
  "member.role": "调整了角色",
  "column.created": "新建了列表",
  "column.updated": "更新了列表",
  "column.deleted": "删除了列表",
  "card.created": "添加了卡片",
  "card.updated": "更新了卡片",
  "card.moved": "移动了卡片",
  "card.archived": "归档了卡片",
  "card.restored": "恢复了卡片",
  "card.deleted": "删除了卡片",
  "card.duplicated": "复制了卡片",
  "card.assigned": "调整了指派",
  "card.responsible": "调整了主负责人",
  "comment.added": "发表了评论",
};

export function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  if (attrs) {
    for (const [key, value] of Object.entries(attrs)) {
      if (value == null || value === false) continue;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key === "html") node.innerHTML = value;
      else node.setAttribute(key, value);
    }
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function safeColor(value, fallback = "#8A4B5A") {
  return /^#[0-9A-Fa-f]{6}$/.test(value || "") ? value : fallback;
}

export function initial(name) {
  const text = (name || "?").trim();
  return text.slice(0, 1).toUpperCase();
}

export function avatar(person, extra = "") {
  return el("span", { class: `avatar ${extra}`.trim(), title: person?.display_name || "" },
    el("img", { src: avatarPath(avatarId(person)), alt: person?.display_name || "用户头像", width: "40", height: "40", decoding: "async" }),
  );
}

export function cardFaces(card, members, limit = 3) {
  const people = members || [];
  const assigned = new Set(card?.assignee_ids || []);
  const leadId = card?.responsible_user_id ?? null;
  const assignedPeople = people.filter((person) => assigned.has(person.id));
  if (leadId == null) return assignedPeople.slice(0, limit).map((person) => ({ person, lead: false }));
  const lead = people.find((person) => person.id === leadId) || null;
  const faces = [];
  if (lead) faces.push({ person: lead, lead: true });
  for (const person of assignedPeople.filter((item) => item.id !== leadId).slice(0, limit)) faces.push({ person, lead: false });
  return faces;
}

export function faceNode(face) {
  const node = avatar(face.person, face.lead ? "is-lead" : "");
  if (face.lead) node.title = `主负责人 ${face.person.display_name || ""}`.trim();
  return node;
}

export function participantMembers(card, members) {
  const people = members || [];
  const leadId = card?.responsible_user_id ?? null;
  if (leadId == null) return people.slice();
  return people.filter((person) => person.id !== leadId);
}

export function responsibleField(card, members, edit) {
  const people = members || [];
  const current = people.find((person) => person.id === card?.responsible_user_id) || null;
  const select = el("select", {
    class: "responsible-select",
    "data-act": "responsible",
    "aria-label": "主负责人",
    disabled: !edit,
  },
    el("option", { value: "", text: "未指定", selected: !current }),
    ...people.map((person) => el("option", {
      value: String(person.id),
      text: person.display_name,
      selected: current?.id === person.id,
    })),
  );
  return el("div", { class: "responsible" }, current ? avatar(current) : null, select);
}

export function dueInfo(value) {
  if (!value) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const due = new Date(`${value}T00:00:00`);
  const diff = Math.round((due - today) / 86400000);
  if (diff < 0) return { text: `延期 ${-diff} 天`, over: true };
  if (diff === 0) return { text: "今天到期", today: true };
  if (diff === 1) return { text: "明天" };
  return { text: `${due.getMonth() + 1}月${due.getDate()}日` };
}

const TWELVE_HOURS = 12 * 3600;

function pad(value) {
  return String(value).padStart(2, "0");
}

function absolute(then) {
  const clock = `${pad(then.getHours())}:${pad(then.getMinutes())}`;
  const date = `${then.getMonth() + 1}月${then.getDate()}日`;
  if (then.getFullYear() === new Date().getFullYear()) return `${date} ${clock}`;
  return `${then.getFullYear()}年${date} ${clock}`;
}

export function relative(iso) {
  if (!iso) return "";
  const then = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  const diff = (Date.now() - then.getTime()) / 1000;
  if (Number.isNaN(diff)) return "";
  if (diff >= TWELVE_HOURS) return absolute(then);
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  return `${Math.floor(diff / 3600)} 小时前`;
}

export function fileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function inline(parent, text) {
  const pattern = /(\*\*([^*]+)\*\*|\*([^*]+)\*|`([^`]+)`|\[([^\]]+)\]\((https?:\/\/[^)\s]+)\))/g;
  let last = 0;
  let match;
  while ((match = pattern.exec(text))) {
    if (match.index > last) parent.append(document.createTextNode(text.slice(last, match.index)));
    if (match[2]) parent.append(el("strong", { text: match[2] }));
    else if (match[3]) parent.append(el("em", { text: match[3] }));
    else if (match[4]) parent.append(el("code", { text: match[4] }));
    else if (match[6]) {
      const link = el("a", { text: match[5], href: match[6], target: "_blank", rel: "noopener noreferrer" });
      parent.append(link);
    }
    last = match.index + match[0].length;
  }
  if (last < text.length) parent.append(document.createTextNode(text.slice(last)));
}

export function markdown(text) {
  const root = el("div", { class: "md" });
  const lines = (text || "").replace(/\r\n/g, "\n").split("\n");
  let list = null;
  const flush = () => {
    list = null;
  };
  for (const line of lines) {
    if (line.startsWith("- ")) {
      if (!list) {
        list = el("ul");
        root.append(list);
      }
      const item = el("li");
      inline(item, line.slice(2));
      list.append(item);
      continue;
    }
    flush();
    if (!line.trim()) {
      root.append(el("div", { class: "md-gap" }));
      continue;
    }
    const paragraph = el("p");
    inline(paragraph, line);
    root.append(paragraph);
  }
  return root;
}

export function canEdit(role, archived) {
  return !archived && ["owner", "admin", "member"].includes(role);
}

export function canAdmin(role) {
  return role === "owner" || role === "admin";
}
