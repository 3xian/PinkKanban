import { AVATAR_GROUPS, AVATARS, avatarId, avatarPath } from "./avatars.js";
import { el } from "./format.js";

export function createAvatarPicker(person) {
  const selected = el("input", { type: "hidden", name: "avatar_id", value: avatarId(person) });
  let group = AVATARS.find((item) => item.id === selected.value).group;
  const choices = el("div", { class: "avatar-choices", role: "group", "aria-label": "预设头像" });
  const caption = el("span", { class: "avatar-caption", "aria-live": "polite" });
  const categories = AVATAR_GROUPS.map((item) => {
    const button = el("button", { type: "button", class: "avatar-category", text: item.name });
    button.addEventListener("click", () => { group = item.id; paint(); });
    return button;
  });

  function paint() {
    categories.forEach((button, index) => button.setAttribute("aria-pressed", String(AVATAR_GROUPS[index].id === group)));
    caption.textContent = `已选：${AVATARS.find((item) => item.id === selected.value).name}`;
    choices.replaceChildren(...AVATARS.filter((item) => item.group === group).map((item) => {
      const button = el("button", {
        type: "button", class: "avatar-choice", "aria-label": item.name,
        "aria-pressed": String(item.id === selected.value), title: item.name,
      }, el("img", { src: avatarPath(item.id), alt: "", width: "56", height: "56" }));
      button.addEventListener("click", () => {
        selected.value = item.id;
        caption.textContent = `已选：${item.name}`;
        choices.querySelectorAll("button").forEach((choice) => choice.setAttribute("aria-pressed", String(choice === button)));
      });
      return button;
    }));
  }

  paint();
  return el("div", { class: "avatar-picker" }, selected,
    el("div", { class: "avatar-categories", role: "group", "aria-label": "头像分类" }, ...categories),
    choices, caption,
  );
}
