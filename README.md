# PinkKanban · 看板

面向小团队的自托管看板，把任务、负责人、截止日期、讨论和附件放在同一张卡片里，从待办一路跟到交付。

适合产品排期、设计改稿、客户项目和日常协作：拖动卡片更新阶段，不必在群聊里翻找进度，也不必用表格单元格维护状态。邀请需对方接受，项目支持只读访问。

**FastAPI + MariaDB · 原生 JavaScript，无前端构建步骤 · Web 与 Android 客户端 · MIT**

本文描述当前源码；线上功能取决于实际部署版本。Android 原生功能与验收范围分别见[客户端说明](android/README.md)和[历史验收记录](android/qa/RESULTS.md)。

[快速开始](#快速开始) · [功能与权限](#功能与权限) · [配置](#配置) · [部署与升级](#部署与升级) · [开发与测试](#开发与测试) · [API](#api)

## 功能与权限

- **看板协作**：列表与卡片拖拽排序、WIP 提示、项目归档与恢复。
- **实时同步**：通过 SSE 接收看板变化通知，局部更新卡片、列表与项目信息；保留滚动、阅读位置和草稿，输入、拖拽与文字选择期间延后同步，断线后自动恢复。
- **任务跟进**：Markdown 描述、优先级、截止日期、主负责人、参与人、标签、清单、完成标记、归档与复制。封面提供需求、开发、界面、数据、测试、修复、部署、安全 8 种图标主题，采用本地 Lucide SVG 与 Radix Colors 浅色配色，任务卡同步展示对应图标与底色。
- **集中沟通**：评论、附件预览、项目与卡片活动记录；PC 端项目动态固定在看板页面右侧并占满页面高度，移动端通过「看板 / 项目动态」双 Tab 切换。通知可打开对应任务或项目，未接受的邀请需先处理。
- **快速定位**：关键词、我的、延期、标签、优先级、完成状态与归档筛选；跨项目「我的任务」。
- **移动端**：响应式网页、触屏长按拖拽；[Android 客户端](android/README.md)提供会话保持、系统返回导航、附件上传与保存、连接重试。

### 角色权限

项目创建者自动成为 `owner`。权限逐级包含：`owner` > `admin` > `member` > `viewer`。

| 角色 | 能做什么 | 边界 |
| --- | --- | --- |
| `owner` 拥有者 | 管理员的全部能力；移交拥有者、删除项目 | 不能修改自己的角色或被移除；退出前必须移交 |
| `admin` 管理员 | 成员的全部能力；邀请与撤回邀请、调整角色、移除成员 | 删除他人的评论与附件需要此级权限 |
| `member` 成员 | 管理列表、卡片、标签和清单；评论、上传附件 | 不能管理项目成员 |
| `viewer` 只读 | 查看看板、卡片详情和活动流 | 不能修改项目内容；仍可处理自己的账号、通知或退出项目 |

### 使用边界

- **主负责人最多一人**，只能选当前项目成员，不改变项目权限。指定后自动加入参与人；换人或清空主负责人不会移除原参与人。「我的」和「我的任务」仍按参与人计算。
- **移交项目需二次确认**：弹窗显示项目与接收人，并提示移交后原拥有者变为管理员；取消或关闭弹窗不会提交移交。
- **WIP 是提醒，不是硬限制**：超出时突出显示列表计数，服务端不阻止移动。项目至少保留一个列表；删除列表时卡片并入相邻列表。
- **筛选开启时禁用拖拽**，避免按可见子集计算排序。鼠标按住即拖，触屏长按 280ms 进入拖拽。
- **任务详情以阅读为主**：首屏展示完成状态、主负责人、截止日期与优先级；描述默认渲染 Markdown，点击编辑后明确保存或取消，保存失败保留草稿。标题与截止日期失焦保存，其余属性变更即时保存。参与人、标签和封面默认只展示当前值，点击管理或更换后才展开选项；新增清单、清单项、标签与评论按需展开。动态默认收起，复制、归档与删除位于顶部「更多」，删除仍需确认。属性保存时只保留真正修改过的未提交字段，未修改字段采用最新接口值，避免回写旧内容；保留展开状态与阅读位置，关闭任务详情后丢弃未提交草稿。手机按核心属性、任务正文、次要属性、动态的顺序展示；只读用户看到信息而非禁用的编辑控件。
- **任务卡展示执行摘要**：展示描述摘要、标签、截止日期、评论和附件计数；有清单时显示真实完成比例与圆点进度。主负责人头像有描边，详情不在参与人区域重复展示主负责人。
- **新建任务使用完整表单**：标题必填，描述、负责人和截止日期选填，所属列表可修改。一次请求保存全部字段；提交失败保留输入，取消或关闭表单丢弃草稿。清单、附件和评论在创建后补充。
- **Android 是在线 WebView 客户端**，不是独立离线看板；不提供离线编辑或后台系统推送。构建、服务地址配置与验收见[客户端文档](android/README.md)。

## 快速开始

以下命令均在仓库根目录执行。Docker Compose **只启动数据库**，Web 服务通过 Python 单独启动。

### 1. 准备环境与配置

需要 Python（建议 3.12，与 CI 一致）、Docker 和 Docker Compose。日常运行不需要 Node.js，也没有前端打包步骤。

Linux / macOS：

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows（命令提示符）：

```bat
copy .env.example .env
```

编辑 `.env`：设置自己的 `SECRET_KEY`，并填写 SMTP 配置。

> **注册需要邮箱验证码。** `SMTP_HOST` 为空时发送验证码接口返回 503，页面虽能打开，新用户仍无法注册。常见配置为端口 587、`SMTP_SSL=0`、`SMTP_TLS=1`；发件人默认使用 `SMTP_USER`，也可显式设置 `SMTP_FROM`。不要在日常运行中开启测试专用的 `MAIL_CAPTURE`。

配置读取自 `.env`，但不会覆盖已有环境变量。完整选项见[配置](#配置)。

### 2. 启动数据库

```bash
docker compose up -d --wait
```

仓库使用 MariaDB 10.11，宿主端口为 **3307**，不占用 3306；数据保存在 Compose 的 `kanban_db` 命名卷中（实际卷名通常带项目名前缀）。默认连接串已写入 `.env.example`。

### 3. 启动 Web 服务

Linux / macOS（已激活上面的虚拟环境）：

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Windows：

```bat
cmd.exe /c run.bat
```

`run.bat` 在缺少 `.venv\Scripts\python.exe` 时自动创建虚拟环境并安装依赖；已有环境更新依赖时，运行 `.venv\Scripts\python.exe -m pip install -r requirements.txt`。

打开 <http://127.0.0.1:8000>，获取邮箱验证码并注册，然后创建项目、添加卡片、邀请协作者。创建项目成功后会收到一条站内通知。

另开终端检查服务和数据库连接：

```bash
curl http://127.0.0.1:8000/api/health
```

正常响应为 `{"ok":true}`。交互式 API 文档位于 <http://127.0.0.1:8000/docs>。

### 常见启动问题

| 现象 | 检查项 |
| --- | --- |
| 数据库连接失败 | `docker compose ps` 是否健康；3307 是否被占用；`DATABASE_URL` 是否与数据库账号一致 |
| 验证码返回 503 | `SMTP_HOST` 是否填写；SMTP 凭据、发件人、端口与 SSL / STARTTLS 是否匹配 |
| 改了 `.env` 仍未生效 | 重启 Web 服务；检查同名环境变量，它们优先于 `.env` |
| 本地 HTTP 登录无法保持 | 本地使用 `APP_SECURE_COOKIE=0`；`1` 仅用于 HTTPS |

## 配置

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | `mysql+pymysql://kanban:kanban@127.0.0.1:3307/kanban?charset=utf8mb4` | 必须包含库名；库不存在时尝试自动创建，账号需有相应权限 |
| `SECRET_KEY` | `dev-only-change-me` | 会话签名密钥；必须替换为自己的长随机值，不能沿用示例值 |
| `APP_TIMEZONE` | `Asia/Shanghai` | 每日项目配额的自然日边界 |
| `DAILY_PROJECT_LIMIT` | `30` | 每人每天最多新建项目数；非整数回退 30，最小 1，超限返回 429 |
| `APP_SECURE_COOKIE` | `0` | `1` 为会话 Cookie 添加 `Secure`，仅在 HTTPS 下开启 |
| `SMTP_HOST` | 空 | 注册验证码 SMTP 主机；为空时发送接口返回 503 |
| `SMTP_PORT` | `587` | SMTP 端口 |
| `SMTP_USER` | 空 | SMTP 登录用户 |
| `SMTP_PASSWORD` | 空 | SMTP 登录口令 |
| `SMTP_FROM` | 同 `SMTP_USER` | 发件人地址 |
| `SMTP_SSL` | `0` | `1` 使用隐式 SSL，常见于端口 465 |
| `SMTP_TLS` | `1` | 非 SSL 时使用 STARTTLS；`0` 关闭 |

## 部署与升级

仓库的 Compose 配置是**开发数据库配置，不是完整的生产部署方案**。

- **更换凭据**：替换 `SECRET_KEY`、MariaDB root 与 `kanban` 密码，同步修改 `DATABASE_URL`。Compose 中的口令为明文开发口令；已有数据卷不会因修改初始化环境变量而自动改密码。
- **限制数据库暴露**：Compose 的 `3307:3306` 未限定监听地址。生产环境应将数据库限制在本机或私有网络，不直接暴露公网。
- **使用 HTTPS**：由反向代理提供 HTTPS，设置 `APP_SECURE_COOKIE=1`；本地启动命令仅监听 `127.0.0.1`。
- **配置发信服务**：SMTP 是注册流程的必要条件，不能以测试捕获模式代替。
- **保持单 worker / 单实例假设**：接口限流与 SSE 看板通知订阅均保存在进程内存中，多 worker 或多副本不会共享；扩展前需接入共享限流存储与发布订阅通道。
- **允许 SSE 长连接**：`/api/projects/{id}/events` 返回 `X-Accel-Buffering: no` 禁用 nginx 响应缓冲，每 15 秒发送心跳。其他代理也需关闭事件流缓冲并允许持续连接。前端连接正常时不定时读取看板；连接异常时每 15 秒读取作为降级，重连后获取最新快照补齐离线变化。
- **持久化与备份**：使用仓库 Compose 时数据库在命名卷中；使用独立 MariaDB 时由数据库部署管理。数据库与 `uploads/` 附件都需备份，附件目录需可写。同步代码时保留 `.env` 和 `uploads/`。

启动会检查数据库，必要时尝试 `CREATE DATABASE`，再通过 `create_all` 创建缺失表。**`create_all` 不会修改已有表结构**；当前启动升级会为 `cards` 补充可空的 `responsible_user_id` 列、索引和外键，为 `users` 补充可空的 `avatar_id` 列，并将 `access_tokens.expires_at` 升级为可空，保留已有数据。数据库账号需有相应 DDL 权限；升级前备份，更新后重启后端。使用名为 `pinkkanban.service` 的 systemd 服务时，重启该服务。

### 限额与附件

| 项目 | 上限 |
| --- | --- |
| 每人每日新建项目 | `DAILY_PROJECT_LIMIT`，默认 30 |
| 每项目列表 / 卡片 / 标签 | 40 / 4000 / 30 |
| 每卡片清单 / 评论 | 20 / 1000 |
| 每清单条目 | 100 |
| 单个附件 | 8 MiB |

附件扩展名白名单见 [`app/constants.py`](app/constants.py)。展示名与存储名分离，落盘名为随机 hex 加原扩展名；事务提交后才删除文件，回滚不删除。

接口按来源 IP 限流：注册 10 次/小时、登录 20 次/10 分钟、邮箱查询 30 次/分钟、验证码 8 次/小时。同一邮箱 60 秒内不能再次获取验证码；验证码 10 分钟有效，连续错误 5 次作废。

## 开发与测试

### 技术栈与目录

| 层 | 选型 / 入口 |
| --- | --- |
| API | FastAPI，[`app/main.py`](app/main.py)，紧凑 UTF-8 JSON 响应 |
| ORM / 数据库 | SQLAlchemy 2 + PyMySQL / MariaDB 10.11 |
| 前端 | [`static/js/`](static/js/) 原生 ES Module + CSS，无打包器 |
| 密码 / 会话 | `hashlib.scrypt`（`n=2**14`）/ HMAC-SHA256 签名 token，存于 Cookie |
| Android | [`android/`](android/README.md)，原生 Java + WebView |
| 测试 / 数据库初始化 | [`tests/`](tests/) / [`deploy/initdb/`](deploy/initdb/) |

### 界面与交互

- **导航**：hash 路由包含项目、看板、我的任务、通知、设置和账号。页面不设顶部工作区栏；通知及未读数位于侧栏导航，账号设置位于侧栏底部。侧栏选中项以白底、左端圆角和轻微投影标识；窄屏通过底部「菜单」打开侧栏，也可使用底部快捷导航。
- **看板**：桌面任务列独立滚动，隐藏列内滚动条；下方还有卡片时显示底部阴影。底部渐变横向滚动条提供更大的点击和拖拽区域。项目动态在右侧独立占列并占满看板页面高度，评论单独展示，其余记录分组折叠。窄屏通过「看板 / 项目动态」双 Tab 切换，长列表在看板区域纵向滚动，横向滚动保留。隐藏看板期间延后更新任务区，切回或恢复桌面布局时应用最新数据并保留阅读位置。
- **详情**：桌面抽屉分为内容区和属性区，窄屏合并为单列；图片附件可预览并打开原图。
- **通知**：点击时标记已读，并按关联信息打开任务或项目；已读通知仍可跳转。邀请接受、拒绝独立处理；未读数为零时隐藏徽标。
- **操作保护**：侧栏开关不重建页面；`Esc` 依次关闭筛选菜单、弹层、抽屉、侧栏。Android 下拉刷新仅允许从主内容顶部的非交互、非嵌套滚动区域开始。
- **品牌与头像**：Web 标识使用 `static/favicon.svg`，Android 使用对应自适应图标资源。24 个预设头像按男生、女生、宠物和机器人分类，老账号按用户 ID 稳定分配默认头像。素材与缓存维护见[头像说明](static/avatars/README.md)。
- **账号与凭证**：桌面表单分栏，窄屏单列。`static/js/tokens.js` 独立管理凭证请求和临时明文；离开账号页或登出时清除明文并中止请求，中止不保证撤销服务端已提交的操作。

### 后端测试

先按[快速开始](#快速开始)准备虚拟环境与数据库，再执行：

```bash
python -m pytest
```

Windows 使用 `.venv/Scripts/python.exe -m pytest`。

> **测试会删除测试库中的全部表。** `tests/conftest.py` 将 `DATABASE_URL` 覆盖为本机 3307 上的 `kanban_test`，每个用例前调用 `truncate_all()` 重建表，并清空限流和邮件捕获状态。不要将测试配置改成生产库，也不要让该端口指向生产数据库。

`kanban_test` 由 [`deploy/initdb/01-test-db.sql`](deploy/initdb/01-test-db.sql) 在数据库卷首次初始化时创建并授权。已有卷不会重跑初始化脚本；缺少测试库时需手动创建并授予 `kanban` 用户权限，不要为此删除含有业务数据的卷。

测试通过 `TestClient` 携带 `X-Kanban: 1`，使用 `MAIL_CAPTURE=1` 捕获验证码，不连接真实 SMTP。覆盖认证、请求头校验、验证码、看板初始化、邀请、角色权限、配额、附件、截止日期、主负责人及任务创建事务。测试范围不等于当前版本已通过，结果以实际运行记录为准。

凭证回归测试使用独立内存 SQLite，不连接 MariaDB：`python -m pytest tests/test_tokens.py -q`。覆盖摘要存储、仅创建时返回明文、Bearer 读写、凭证管理的 Cookie 限制、跨用户撤销隔离、项目权限、有限期过期与无限期持续有效、撤销失效、认证优先级及输入边界。

SSE 回归使用临时 SQLite 与本机 HTTP 服务，不连接 MariaDB：`python -m pytest tests/test_live.py -q`。覆盖事务提交后通知、回滚不通知、项目隔离、标签与头像变化、订阅清理及成员权限撤销。数据库依赖使用 FastAPI 0.121 起支持的 function scope，确保事务提交后才返回成功响应与发送通知。

### 前端与浏览器回归

前端测试需要 Node.js（CI 使用 24），不影响日常运行：

```bash
node --test tests/*.test.mjs
```

浏览器回归使用本地静态服务器和模拟 API，不访问数据库，也不由 pytest 自动收集：

```bash
python -m pip install playwright
python -m playwright install chromium
python tests/startup_browser.py
python tests/desktop_browser.py
```

| 脚本 | 范围 | 浏览器配置 |
| --- | --- | --- |
| `startup_browser.py` | 启动恢复、账号、SSE、节点与阅读位置保留、交互保护 | 支持 `CHROMIUM_PATH`，默认 Playwright Chromium |
| `desktop_browser.py` | 响应式布局、任务创建、通知跳转、列底阴影、活动栏与附件预览 | 使用 Playwright Chromium |

创建表单打开期间延后远端更新，关闭后恢复同步；对应回归验证草稿保留及取消后的列表刷新。后端事务用例需要本地 `kanban_test` 数据库。

[CI](.github/workflows/ci.yml) 执行后端、JavaScript 单测、`startup_browser.py`、Android QA 边界检查及 Android 构建；同时执行 `desktop_browser.py` 验证布局和任务交互。[发布流程](.github/workflows/release.yml)签名并发布 APK，不部署服务器。Android 本地验收见[客户端文档](android/README.md)。

## API

服务运行后通过 [`/docs`](http://127.0.0.1:8000/docs) 查看完整请求与响应模型。

**所有 `/api/` 下的 `POST`、`PUT`、`PATCH`、`DELETE` 请求必须携带 `X-Kanban: 1`，缺失返回 403。** 该自定义头用于 CSRF 防护，不代替登录和项目权限校验；前端 `static/js/api.js` 统一添加。

### Agent 凭证

登录网页后，点击侧栏底部的账号进入「Agent 凭证」，填写名称与有效天数（1–365 天，默认 30 天），或勾选「永不过期」，即可生成独立凭证。完整密钥只在创建成功时返回并临时显示，关闭明文、离开账户页或登出后不可找回；数据库仅保存 SHA-256 摘要。列表可查看名称和到期时间（或「永不过期」）、撤销凭证，过期或撤销后认证返回 401。无限期凭证不会自动失效，请在不再使用时主动撤销；现有凭证的到期时间不变。

**凭证代表用户本人，拥有用户当前的全部权限，包括有权执行的删除操作。** 仅交给可信任的 agent。退出网页登录不会撤销凭证，需在账户页单独撤销；项目访问与角色校验继续复用现有权限模型。

Agent 调用现有 API 时携带 `Authorization: Bearer <token>`，写操作仍必须携带 `X-Kanban: 1`，无需用户密码或浏览器 Cookie。网页继续使用 Cookie。若请求同时带 Cookie 和 Authorization，以 Authorization 为准；无效凭证不会回退到 Cookie。

```bash
# 通过运行环境注入 KANBAN_TOKEN，不要写入代码或提交到仓库。
curl https://kanban.faweisi.com/api/projects \
  -H "Authorization: Bearer $KANBAN_TOKEN"

curl https://kanban.faweisi.com/api/projects \
  -H "Authorization: Bearer $KANBAN_TOKEN" \
  -H "X-Kanban: 1" \
  -H "Content-Type: application/json" \
  --data '{"name":"Agent 项目"}'
```

凭证管理接口仅接受网页登录 Cookie，不接受 Bearer 认证，避免 agent 自行创建新的长期凭证；创建/列表响应标记 `Cache-Control: no-store`。数据库结构升级见[部署与升级](#部署与升级)。


<details>
<summary>主要端点速查</summary>

同一行中的缩写路径沿用该行第一个端点的资源前缀。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/register`、`/login`、`/logout` | 注册、登录、登出；注册需 6 位邮箱验证码 |
| POST | `/api/auth/code` | 向未注册邮箱发送验证码 |
| GET / PATCH | `/api/auth/me` | 读取 / 更新自己的资料 |
| POST | `/api/auth/password` | 修改密码 |
| GET / POST | `/api/auth/tokens` | 凭证列表 / 创建；创建体为 `{"name":"我的 Agent","expires_in_days":30}`；设为 `null` 表示永不过期，返回的 `expires_at` 也为 `null`；只有创建响应含 `token` |
| DELETE | `/api/auth/tokens/{id}` | 撤销自己的凭证 |
| GET | `/api/bootstrap` | 用户、项目列表、未读数、配额 |
| GET | `/api/projects/{id}/events` | SSE 看板变化通知；需项目访问权限，连接建立或重连发送 `ready`，提交变化发送 `change`，失去权限发送 `unavailable` 后关闭；通知不包含业务数据 |
| GET / POST | `/api/projects` | 项目列表 / 新建；`?archived=true` 查看归档 |
| GET / PATCH / DELETE | `/api/projects/{id}` | 详情 / 修改 / 删除 |
| POST | `/api/projects/{id}/archive`、`restore`、`transfer`、`leave` | 归档、恢复、移交、退出 |
| POST | `/api/projects/{id}/invites` | 发出邀请 |
| POST | `/api/projects/{id}/invites/{note_id}/cancel` | 撤回邀请 |
| PATCH / DELETE | `/api/projects/{id}/members/{member_id}` | 修改角色 / 移除成员 |
| GET | `/api/projects/{id}/activity` | 项目活动流 |
| GET | `/api/projects/{id}/board` | 项目、角色、成员、标签、列表与卡片 |
| POST | `/api/projects/{id}/columns`、`labels` | 新建列表、标签 |
| POST | `/api/projects/{id}/cards` | 新建任务；必填 `column_id`、`title`，可选 `description`、`due_on`、`responsible_user_id`；在同一事务内保存 |
| POST | `/api/projects/{id}/columns/reorder` | 列表排序 |
| PATCH / DELETE | `/api/columns/{id}`、`/api/labels/{id}` | 修改 / 删除列表与标签 |
| GET / PATCH / DELETE | `/api/cards/{id}` | 详情 / 修改 / 删除；主负责人字段 `responsible_user_id` 可设成员 id，`null` 清空，省略不变 |
| POST | `/api/cards/{id}/move`、`archive`、`restore`、`duplicate` | 移动、归档、恢复、复制；复制保留仍在项目中的主负责人和参与人 |
| PUT | `/api/cards/{id}/labels`、`assignees` | 全量替换标签 / 参与人；移除当前主负责人时同步清空该字段 |
| POST | `/api/cards/{id}/checklists`、`comments`、`attachments` | 添加清单 / 评论 / 附件 |
| PATCH / DELETE | `/api/checklists/{id}`、`/api/checklist-items/{id}`、`/api/comments/{id}` | 修改 / 删除子资源 |
| POST | `/api/checklists/{id}/items` | 添加清单条目 |
| DELETE | `/api/attachments/{id}` | 删除附件 |
| GET | `/api/attachments/{id}/file` | 下载；图片扩展名使用 inline，其余使用 attachment |
| GET | `/api/notifications` | 最近 80 条通知 |
| POST | `/api/notifications/{id}/accept`、`reject`、`read` | 处理邀请 / 标记已读 |
| POST | `/api/notifications/read-all` | 全部标记已读 |
| GET | `/api/me/cards` | 我的任务；`?q=` 按标题过滤，上限 200 |
| GET | `/api/users/lookup` | 按邮箱查用户，不存在返回 404 |
| GET | `/api/health` | 探活，执行数据库 `SELECT 1` |

</details>

### 权限实现

`ROLE_RANK` 为 `viewer 1 < member 2 < admin 3 < owner 4`。`app/services/base.py` 提供统一校验入口：

- `require_access`：非成员返回 404，避免泄露项目是否存在；角色不足返回 403；归档项目拒绝写入，返回 409。
- `begin_write`：在项目行上执行 `SELECT ... FOR UPDATE`，串行化同一项目的并发写入。
- `_require_card`：由卡片反查项目，复用访问校验与写锁。

## 许可证

[MIT](LICENSE) © 2026 Pink。
