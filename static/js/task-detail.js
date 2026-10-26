import { PRIORITIES, avatar, dueInfo, el, markdown, participantMembers, relative, responsibleField } from "./format.js";
import { icon as glyph } from "./icons.js";
import { COVER_THEMES, coverTheme } from "./covers.js";

function button(text, attrs = {}, ...children) {
  return el("button", { type: "button", ...attrs }, text, ...children);
}

function empty(text) {
  return el("p", { class: "detail-empty muted", text });
}

function heading(text, action = null) {
  return el("div", { class: "detail-heading" }, el("h3", { text }), action);
}

function picker(key, label, value, ...options) {
  return el("details", { class: "detail-picker", "data-detail-key": key, "data-detail-picker": "" },
    el("summary", { class: "detail-value", "aria-label": `${label}：${value}` }, value),
    el("div", { class: "detail-options" }, ...options),
  );
}

function addForm(key, label, form, className = "") {
  return el("details", { class: `detail-add ${className}`.trim(), "data-detail-key": key },
    el("summary", { text: label }), form,
  );
}

function form(kind, draft, className, ...children) {
  return el("form", { "data-form": kind, "data-draft-key": draft, class: className }, ...children);
}

function submit(text) {
  return el("button", { type: "submit", class: "btn-primary btn-tiny", text });
}

function coverSymbol(theme) {
  return el("span", {
    class: "cover-symbol", "aria-hidden": "true",
    style: `--cover-icon:url('/static/icons/covers/${theme.icon}.svg');color:${theme.ink}`,
  });
}

function checklistBlock(list, edit) {
  const items = list.items || [];
  return el("div", { class: "checklist" },
    el("div", { class: "checklist-head" }, el("strong", { text: list.title }), el("span", { class: "count", text: `${items.filter((item) => item.done).length}/${items.length}` })),
    ...items.map((item) => el("div", { class: "check-item" },
      edit ? el("label", { class: "check" }, el("input", { type: "checkbox", "data-act": "item", "data-id": item.id, checked: item.done, "aria-label": `完成清单项：${item.text}` }), el("span", { text: item.text }))
        : el("span", { class: "detail-read-value", text: `${item.done ? "已完成" : "未完成"} · ${item.text}` }),
      edit ? button(null, { class: "icon-btn icon-btn-sm check-remove", "data-act": "delete-item", "data-id": item.id, "aria-label": `删除清单项：${item.text}` }, glyph("trash")) : null,
    )),
    edit ? addForm(`item-${list.id}`, "添加清单项", form("item", `item-${list.id}`, "composer",
      el("input", { type: "hidden", name: "checklist_id", value: list.id }),
      el("input", { name: "text", placeholder: "清单项", "aria-label": `${list.title}：新清单项`, required: true }), submit("添加"),
    )) : null,
  );
}

export function taskDetail({ data, board, ui = {}, activityList, attachmentSection }) {
  const card = data.card;
  const edit = Boolean(card.can_edit);
  const members = board?.members || [];
  const labels = board?.labels || [];
  const participants = participantMembers(card, members);
  const selectedParticipants = participants.filter((person) => (card.assignee_ids || []).includes(person.id));
  const selectedLabels = labels.filter((label) => (card.label_ids || []).includes(label.id));
  const responsible = members.find((person) => person.id === card.responsible_user_id);
  const priority = PRIORITIES.find(([value]) => value === card.priority)?.[1] || "无";
  const due = card.done ? null : dueInfo(card.due_on);
  const dueText = card.due_on ? `${card.due_on}${due?.over || due?.today ? ` · ${due.text}` : ""}` : "未设置";
  const theme = coverTheme(card.cover_color);
  const coverName = theme?.name || (card.cover_color ? "自定义封面" : "无封面");
  const readValue = (text) => el("span", { class: "detail-read-value", text });
  const prop = (label, value) => el("div", { class: "prop" }, el("span", { class: "prop-k", text: label }), value);
  const more = edit ? el("details", { class: "task-more", "data-detail-key": "more", "data-detail-picker": "" },
    el("summary", { "aria-label": "更多任务操作", text: "更多" }),
    el("div", { class: "detail-options" },
      button("复制任务", { class: "btn-ghost", "data-act": "duplicate" }),
      button(card.archived ? "恢复任务" : "归档任务", { class: "btn-ghost", "data-act": card.archived ? "restore-card" : "archive-card" }),
      el("div", { class: "detail-danger" }, button("删除任务", { class: "btn-danger", "data-act": "delete-card" })),
    ),
  ) : null;

  const description = el("section", { class: "section section-desc" },
    heading("描述", edit && !ui.descriptionEditing && card.description ? button("编辑", { class: "btn-ghost btn-tiny", "data-act": "edit-description", "aria-label": "编辑描述" }) : null),
  );
  if (edit && ui.descriptionEditing) {
    description.append(form("description", "description", "description-form",
      el("textarea", { class: "desc-input", name: "description", text: card.description || "", "aria-label": "任务描述" }),
      el("div", { class: "description-actions" }, submit("保存描述"), button("取消", { class: "btn-ghost btn-tiny", "data-act": "cancel-description" })),
    ));
  } else if (card.description) {
    const preview = markdown(card.description);
    if (edit) preview.classList.add("description-read");
    description.append(preview);
  } else {
    description.append(edit ? button("添加描述", { class: "btn-ghost detail-empty", "data-act": "edit-description" }) : empty("暂无描述"));
  }

  const labelPicker = edit ? picker("labels", "管理标签", "管理标签",
    el("div", { class: "pills", role: "group", "aria-label": "选择任务标签" }, ...labels.map((label) => {
      const on = (card.label_ids || []).includes(label.id);
      return button(null, { class: on ? "pill is-on" : "pill", "data-act": "toggle-label", "data-id": label.id, "aria-pressed": String(on) },
        el("span", { class: "label-mark", "aria-hidden": "true" }, glyph("check")), el("span", { class: "label-name", text: label.name }));
    })),
    !labels.length ? empty("暂无可选标签") : null,
    addForm("new-label", "创建标签", form("label", "label", "composer label-composer",
      el("input", { name: "name", placeholder: "输入新标签名称", "aria-label": "新标签名称", maxlength: "24", required: true }), submit("创建"),
    )),
  ) : null;

  const participantPicker = edit ? picker("participants", "管理参与人", "管理参与人",
    el("div", { class: "assignees", role: "group", "aria-label": "选择任务参与人" }, ...participants.map((person) => {
      const on = (card.assignee_ids || []).includes(person.id);
      return button(null, { class: on ? "assignee is-on" : "assignee", "data-act": "toggle-assignee", "data-id": person.id, "aria-pressed": String(on) }, avatar(person), person.display_name);
    })),
    !participants.length ? empty("暂无可选参与人") : null,
  ) : null;

  const coverPicker = edit ? picker("cover", "更改封面", "更改封面",
    el("div", { class: "cover-picker", role: "group", "aria-label": "选择任务封面" },
      button(null, { class: card.cover_color ? "cover-option cover-none" : "cover-option cover-none is-on", "data-act": "cover", "data-color": "", "aria-pressed": String(!card.cover_color) }, glyph("close"), el("span", { text: "无封面" })),
      ...COVER_THEMES.map((option) => button(null, {
        class: theme === option ? "cover-option is-on" : "cover-option", "data-act": "cover", "data-color": option.value,
        "aria-label": `封面：${option.name}`, "aria-pressed": String(theme === option),
        style: `--cover-bg:${option.background};--cover-selected:${option.selected};--cover-border:${option.border};--cover-ink:${option.ink}`,
      }, coverSymbol(option), el("span", { text: option.name }), el("span", { class: "cover-check", "aria-hidden": "true" }, glyph("check")))),
    ),
  ) : null;

  return el("article", { class: "drawer-panel" },
    el("div", { class: "drawer-top" },
      el("i", { class: "sheet-handle", "aria-hidden": "true" }),
      el("div", { class: "drawer-top-row" },
        el("span", { class: "crumb", text: [board?.project?.name, board?.columns?.find((column) => column.id === card.column_id)?.name].filter(Boolean).join(" / ") }),
        el("div", { class: "drawer-actions" }, more, button(null, { class: "icon-btn", "data-act": "close-drawer", "aria-label": "关闭任务详情" }, glyph("close"))),
      ),
      edit ? el("textarea", { class: "drawer-title", "data-save": "title", name: "title", rows: "1", text: card.title, "aria-label": "任务标题" }) : el("h2", { class: "drawer-title", text: card.title }),
    ),
    el("div", { class: "drawer-body" },
      el("div", { class: "task-core props" },
        prop("状态", edit ? el("label", { class: "check detail-value" },
          el("input", { type: "checkbox", "data-act": "done", checked: card.done }), card.done ? "已完成" : "未完成",
        ) : readValue(card.done ? "已完成" : "未完成")),
        prop("主负责人", edit ? picker("responsible", "主负责人", responsible?.display_name || "未指定", responsibleField(card, members, true))
          : el("span", { class: "detail-read-value responsible" }, responsible ? avatar(responsible) : null, responsible?.display_name || "未指定")),
        prop("截止日期", edit ? picker("due", "截止日期", dueText,
          el("label", { class: "field" }, el("span", { text: "截止日期" }), el("input", { type: "date", "data-save": "due", name: "due_on", value: card.due_on || "", "aria-label": "任务截止日期" })),
        ) : readValue(dueText)),
        prop("优先级", edit ? picker("priority", "优先级", priority,
          el("div", { class: "prio", role: "group", "aria-label": "选择任务优先级" }, ...PRIORITIES.map(([value, label]) => button(label, { class: card.priority === value ? "is-on" : "", "data-act": "priority", "data-value": value, "aria-pressed": String(card.priority === value) }))),
        ) : readValue(priority)),
      ),
      el("div", { class: "drawer-content" },
        description,
        el("section", { class: "section" }, heading("清单"),
          ...(data.checklists || []).map((list) => checklistBlock(list, edit)),
          !data.checklists?.length ? empty("暂无清单") : null,
          edit ? addForm("new-checklist", "添加清单", form("checklist", "checklist", "composer", el("input", { name: "title", placeholder: "清单标题", "aria-label": "新清单标题", required: true }), submit("添加"))) : null,
        ),
        attachmentSection(data.attachments || [], edit),
        el("section", { class: "section" }, heading("评论"),
          ...(data.comments || []).map((comment) => el("article", { class: "comment" },
            el("header", {}, comment.user ? avatar(comment.user) : null, el("strong", { text: comment.user?.display_name || "成员" }),
              el("span", { class: "muted", text: relative(comment.created_at) + (comment.edited ? " · 已编辑" : "") }),
              comment.mine ? button(null, { class: "icon-btn icon-btn-sm check-remove", "data-act": "delete-comment", "data-id": comment.id, "aria-label": "删除自己的评论" }, glyph("trash")) : null,
            ), el("p", { text: comment.body }),
          )),
          !data.comments?.length ? empty("暂无评论") : null,
          edit ? addForm("new-comment", "写评论", form("comment", "comment", "comment-form",
            el("textarea", { name: "body", placeholder: "写评论，用 @显示名 提及成员", "aria-label": "评论内容", required: true }), submit("发送"),
          )) : null,
        ),
      ),
      el("aside", { class: "drawer-side", "aria-label": "任务参与人、标签与封面" },
        el("section", { class: "section" }, heading("参与人"),
          el("div", { class: "assignees" }, ...selectedParticipants.map((person) => el("span", { class: "assignee is-on" }, avatar(person), person.display_name))),
          !selectedParticipants.length ? empty("暂无参与人") : null, participantPicker,
        ),
        el("section", { class: "section label-section" }, heading("标签"),
          el("div", { class: "pills", "aria-label": "当前任务标签" }, ...selectedLabels.map((label) => el("span", { class: "pill is-on" }, el("span", { class: "label-name", text: label.name })))),
          !selectedLabels.length ? empty("暂无标签") : null, labelPicker,
        ),
        el("section", { class: "section" }, heading("封面"), el("div", { class: "detail-read-value" }, theme ? coverSymbol(theme) : null, coverName), coverPicker),
      ),
      el("details", { class: "section detail-activity", "data-detail-key": "activity" }, el("summary", { text: "动态" }), activityList(data.activity || [])),
    ),
  );
}
