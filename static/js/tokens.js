import { api } from "./api.js";
import { el } from "./format.js";

export function createTokenPanel(onUnauthorized) {
  const controller = new AbortController();
  let disposed = false;
  let busy = false;
  let items = [];
  let created = null;
  let error = "";

  const name = el("input", { name: "name", required: true, maxlength: "60", placeholder: "例如：我的 Agent" });
  const days = el("input", { name: "expires_in_days", type: "number", min: "1", max: "365", step: "1", value: "30", required: true });
  const unlimited = el("input", { type: "checkbox", name: "unlimited" });
  unlimited.addEventListener("change", () => { days.disabled = unlimited.checked; });
  const submit = el("button", { type: "submit", class: "btn-primary", text: "生成凭证" });
  const form = el("form", { "data-token-form": "1" },
    el("label", { class: "field" }, "名称", name),
    el("label", { class: "field" }, "有效天数（1–365）", days),
    el("label", { class: "check" }, unlimited, "永不过期"),
    submit,
  );
  const secret = el("div");
  const refresh = el("button", { type: "button", class: "btn-tiny", text: "刷新列表" });
  const status = el("p", { class: "muted", role: "status" });
  const list = el("div");
  const node = el("div", { class: "account-block", "data-token-panel": "1" },
    el("h3", { text: "Agent 凭证" }),
    el("p", { class: "muted", text: "凭证与本人拥有相同权限，包括删除数据。仅交给可信任的 Agent；不再使用时请撤销。" }),
    form,
    secret,
    el("div", { class: "section" },
      el("div", { class: "split" }, el("h3", { text: "已创建的凭证" }), refresh),
      status,
      list,
    ),
  );

  function closeSecret() {
    created = null;
    const input = secret.querySelector("input");
    if (input) input.value = "";
    secret.replaceChildren();
  }

  function showSecret() {
    const close = el("button", { type: "button", class: "btn-ghost", text: "我已保存，关闭明文" });
    close.addEventListener("click", closeSecret);
    secret.replaceChildren(el("div", { class: "section", "data-token-secret": "1", role: "status" },
      el("p", { text: "请现在复制并妥善保存。明文仅在此临时显示；关闭、离开账户页或登出后不可找回。" }),
      el("label", { class: "field" }, "新凭证（可手工选择复制）", el("input", { value: created.token, readonly: true, autocomplete: "off", spellcheck: "false", "aria-label": "新凭证明文" })),
      close,
    ));
  }

  function paintList() {
    submit.disabled = busy;
    refresh.disabled = busy;
    refresh.textContent = error ? "重试加载" : "刷新列表";
    status.textContent = busy ? "正在处理…" : error || (items.length ? "" : "暂无凭证。");
    list.replaceChildren(...items.map((token) => {
      const revoke = el("button", { type: "button", class: "btn-tiny btn-danger", disabled: busy, text: "撤销" });
      revoke.addEventListener("click", () => perform(async () => {
        await api(`/api/auth/tokens/${token.id}`, { method: "DELETE", signal: controller.signal });
        if (disposed) return;
        items = items.filter((item) => item.id !== token.id);
        if (created?.id === token.id) closeSecret();
      }));
      return el("div", { class: "token-row" },
        el("div", { class: "token-meta" }, el("strong", { text: token.name }), el("div", { class: "muted", text: token.expires_at === null ? "永不过期" : `到期：${new Date(token.expires_at).toLocaleString()}${new Date(token.expires_at).getTime() <= Date.now() ? " · 已过期" : ""}` })),
        revoke,
      );
    }));
  }

  // One operation at a time: list refreshes cannot race with creation or revocation.
  async function perform(action) {
    if (disposed || busy) return;
    busy = true;
    error = "";
    paintList();
    try {
      await action();
    } catch (failure) {
      if (disposed) return;
      error = failure.message || "请求失败，请重试。";
      if (failure.status === 401) onUnauthorized();
    } finally {
      busy = false;
      if (!disposed) paintList();
    }
  }

  async function load() {
    const data = await api("/api/auth/tokens", { signal: controller.signal });
    if (!disposed) items = data.items;
  }

  refresh.addEventListener("click", () => perform(load));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void perform(async () => {
      const result = await api("/api/auth/tokens", {
        method: "POST",
        body: { name: name.value, expires_in_days: unlimited.checked ? null : Number(days.value) },
        signal: controller.signal,
      });
      if (disposed) return;
      const { token, ...metadata } = result;
      items.unshift(metadata);
      closeSecret();
      created = { id: metadata.id, token };
      showSecret();
      form.reset();
      days.disabled = false;
    });
  });
  void perform(load);

  return {
    node,
    destroy() {
      disposed = true;
      controller.abort();
      closeSecret();
      node.replaceChildren();
    },
  };
}
