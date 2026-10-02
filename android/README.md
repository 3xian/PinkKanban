# 看板 Android

原生 Java Android 工程，应用名 **看板**，默认服务 `https://kanban.faweisi.com`。首版使用 WebView 承载现有移动端界面，项目、看板、任务、通知、成员管理、清单和评论与网页共用功能和权限。最低 Android 8.0（API 26），编译/目标 API 36。

Android 侧不显示原生顶栏，提供页面顶部下拉刷新、自适应系统栏与键盘、断网/服务错误重试、登录 Cookie 保持、返回键依次关闭弹层/卡片/侧边栏并返回上个页面、文件选择上传，以及带登录会话的附件保存。横向滑动和网页内独立滚动区域不会触发刷新。外部链接交给系统浏览器，附件使用系统“保存到”选择器，无需存储或相机权限。

这是在线客户端；没有离线编辑、后台系统推送或独立原生看板 UI。服务更新会同步反映在客户端。首次联网需要设备上的 Android System WebView 可用。

## 构建

在 Android Studio 中打开本目录，使用 JDK 17、SDK Platform 36 和 Build Tools 35.0.0。Gradle Wrapper 为 8.13，Android Gradle Plugin 为 8.13.2（[官方兼容信息](https://developer.android.com/build/releases/agp-8-13-0-release-notes)）。

`local.properties` 不入库，按本机 SDK 位置设置，例如：

```properties
sdk.dir=F\:/AndroidSDK
```

从仓库根目录执行（Windows）：

```powershell
cmd.exe /c android\gradlew.bat -p android assembleDebug testDebugUnitTest lintDebug
```

调试 APK：`app/build/outputs/apk/debug/app-debug.apk`，包名 `com.faweisi.kanban.debug`。正式包名 `com.faweisi.kanban`，版本 `1.0.0`。正式构建：

```powershell
cmd.exe /c android\gradlew.bat -p android assembleRelease lintRelease
```

Release 默认未签名，使用 Android Studio 的 **Generate Signed App Bundle / APK** 和自己的发布密钥签名；密钥文件与口令不要入库。Debug 使用自动生成的开发密钥，适合本机安装验收，不用于商店发布。

## 自动构建与发布

GitHub Actions 的 `CI` 在分支 push、PR 和手动运行时检查后端 API、网页单测、浏览器启动流程、QA 服务边界，并构建 Debug / Release APK、运行 Android 单测和 Lint。后端只使用 Actions 临时 MariaDB 的 `kanban_test` 库；普通 CI 不读取发布密钥。APK 和 Android 检查报告保存在运行的 Artifacts 中。

发布前修改 `app/build.gradle` 的 `versionName` 和递增的 `versionCode`，提交到 `main`，再推送对应的 `vMAJOR.MINOR.PATCH` 标签。例如版本名 `1.0.1` 对应标签 `v1.0.1`。`Android Release` 会检查标签属于 `main` 历史、重新运行完整 CI、确认 APK 版本与标签一致、签名并创建 GitHub Release（已有 Release 则更新 APK 和校验附件）。它不会部署服务器。

仓库 Secrets：`ANDROID_KEYSTORE_BASE64`（密钥库文件的 Base64）、`ANDROID_KEY_ALIAS`、`ANDROID_STORE_PASSWORD`、`ANDROID_KEY_PASSWORD`。必须沿用现有发布密钥，不要每次生成新密钥。签名仅在独立发布任务中进行，密钥临时文件会清除。

也可以手动运行 `Android Release`：`publish=false` 默认验证所选分支并生成签名 Artifact，标签字段指定预期 APK 版本；`publish=true` 则构建标签所指向的提交并更新 GitHub Release。试运行当前分支时可填 `v1.0.0`，无需移动现有标签。

## 本地验收

测试服务器仅使用内存模拟数据、现有静态页面，不读取 `.env`，不连接数据库或生产 API：

```powershell
python android/qa/server.py --port 8765
cmd.exe /c android\gradlew.bat -p android assembleDebug -PkanbanUrl=http://10.0.2.2:8765
F:/AndroidSDK/platform-tools/adb.exe -s emulator-5554 install -r android/app/build/outputs/apk/debug/app-debug.apk
F:/AndroidSDK/platform-tools/adb.exe -s emulator-5554 shell am start -n com.faweisi.kanban.debug/com.faweisi.kanban.MainActivity
```

模拟登录：`android@example.test` / `android-qa-pass`。服务只模拟验收所需的登录、项目、看板、卡片修改、附件上传下载和空通知/任务，其他操作会返回 404。

`python android/qa/device.py dump` 输出 UI 文本和边界；`tap "文本"` 根据当前 UI 树定位；`screenshot android/qa-output/screen.png` 保存截图。可传 `--adb` 和 `--serial` 指定环境。选择附件 `android-qa.txt` 下载后再上传，可验证上传内容；服务器验证会话 Cookie 和写操作 `X-Kanban: 1`。

静态资源访问边界回归：`python -m unittest discover -s android/qa -p test_server.py`；网页返回导航回归：`node --test tests/navigation.test.mjs`。QA 服务只提供首页和 `/static/` 文件，拒绝仓库文件、目录列表及目录遍历。

检查登录、键盘输入、卡片打开、返回键关闭卡片、返回项目、刷新与重启保持登录、附件保存/取消/上传、停止本地服务器后刷新显示重试，再启动服务器并重试恢复。测试完去掉 `-PkanbanUrl` 重新构建，避免交付模拟服务器版本。

## 安全边界

仅配置的同源页面在 WebView 内打开，不暴露 JavaScript 原生桥。HTTPS 证书错误直接拒绝，不加载混合 HTTP 内容；文件系统访问关闭，第三方 Cookie 禁用，Release 禁止 WebView 调试。带 Cookie 的原生下载仅允许 `/api/attachments/{数字ID}/file`，拒绝重定向，避免会话被转发到外部站点。备份与设备迁移排除应用私有数据。

上传只接收已取得显式读取授权的 `content://` URI，并拒绝本应用提供的资源。系统返回和 Escape 共用网页的 `window.kanbanNavigation.handleBack()`；网页通过 `window.kanbanGestures.canPullRefreshAt(x, y)` 判断触点是否允许刷新，坐标为可见区域宽高的比例。发布此客户端前需先更新服务端静态页面，旧页面缺少这些入口时仅支持 WebView 历史返回，并禁用下拉刷新以避免抢占拖拽。

`-PkanbanUrl=https://其他域名` 可配置其他部署；HTTP 仅 Debug 的 localhost、127.0.0.1、10.0.2.2 可用，Release 必须 HTTPS。更换服务后建议清空应用数据，避免保留旧服务的页面状态。
