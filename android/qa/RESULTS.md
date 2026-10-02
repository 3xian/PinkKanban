# 首版验收记录

日期：2026-10-02。环境：Windows / JDK 17 / API 35 Android 模拟器。

- Debug APK 和 R8 压缩的未签名 Release APK 均构建成功。
- `testDebugUnitTest`：4 项通过，覆盖同源边界、附件端点、Debug 本地 HTTP 和外部链接协议限制。
- `lintDebug`、`lintRelease` 通过（保留最低版本资源目录提示）。
- 本地内存服务：登录成功，项目和看板正常加载，卡片详情打开后系统返回关闭详情，重启应用保留会话。
- 系统“保存到”成功保存 `android-qa.txt`，通过 adb 读取文件内容为 `Android QA passed`。
- 系统文件选择器重新选择该文件，服务器检查 multipart 文件内容和会话/CSRF 请求头，卡片展示新增附件。
- 停止本地服务时观察到连接错误重试界面；验收修正了 hash 路由刷新未真正重新请求页面的问题，并增加首次连接超时和可见页面提交处理。

最终交付 Debug APK 编译配置已恢复 `https://kanban.faweisi.com`。正式服务根页面从开发机 HTTP 检查返回 200；没有使用生产账号做写操作。最后的超时/提交处理改动通过构建和 Lint，模拟器完整断网再恢复流程仍需补充回归。Android 8.0 与 Android 16 真机、正式发布签名、系统后台推送未做验收。
