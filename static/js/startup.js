// This small entry point keeps the HTML fallback usable even if an asset fails.
const styles = document.getElementById("app-styles");
const fallback = document.querySelector(".startup");
const message = document.getElementById("startup-message");
fallback.querySelector("a").addEventListener("click", (event) => {
  event.preventDefault();
  location.reload();
});

function waitForStyles() {
  return new Promise((resolve, reject) => {
    const loaded = () => {
      styles.media = "all";
      resolve();
    };
    styles.addEventListener("load", loaded, { once: true });
    styles.addEventListener("error", () => reject(new Error("页面样式加载失败，请重新加载。")), { once: true });
    if (styles.sheet) loaded();
  });
}

async function start() {
  let timer;
  try {
    const [module] = await Promise.race([
      Promise.all([import("./app.js"), waitForStyles()]),
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error("页面资源加载超时，请检查网络后重新加载。")), 20000);
      }),
    ]);
    clearTimeout(timer);
    await module.boot();
    // Optional web fonts must never block first paint or app initialization.
    const fonts = document.createElement("link");
    fonts.rel = "stylesheet";
    fonts.href = "https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;600;700&family=Outfit:wght@400;500;600;700&display=swap";
    document.head.append(fonts);
  } catch (error) {
    document.getElementById("app").replaceChildren(fallback);
    message.textContent = error.message || "看板暂时无法连接，请检查网络后重新加载。";
    message.setAttribute("role", "alert");
  } finally {
    clearTimeout(timer);
  }
}

start();
