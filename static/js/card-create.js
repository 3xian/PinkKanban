import { el } from "./format.js";

export function cardCreateFields(board, columnId) {
  return [
    el("p", { class: "muted", text: "把要做的事写成任务。标题必填，其他信息可以现在填写，也可以稍后补充。" }),
    el("label", { class: "field" }, "任务标题（必填）", el("input", {
      name: "title", required: true, maxlength: "180", "data-autofocus": "1",
      placeholder: "例如：完成首页设计并交付评审",
    })),
    el("label", { class: "field" }, "任务描述（选填）", el("textarea", {
      name: "description", rows: "4", maxlength: "20000", placeholder: "补充任务背景、具体要求或完成标准",
    })),
    el("label", { class: "field" }, "所属列表", el("select", { name: "column_id" },
      ...board.columns.map((column) => el("option", { value: column.id, text: column.name, selected: column.id === columnId })),
    )),
    el("label", { class: "field" }, "负责人（选填）", el("select", { name: "responsible_user_id" },
      el("option", { value: "", text: "暂不指定" }),
      ...board.members.map((person) => el("option", { value: person.id, text: person.display_name })),
    )),
    el("label", { class: "field" }, "截止日期（选填）", el("input", { name: "due_on", type: "date" })),
    el("p", { class: "muted", text: "创建后可在任务详情中添加清单、附件和评论。" }),
  ];
}
