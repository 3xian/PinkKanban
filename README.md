# 看板

看板适合小团队把一件事从开始跟到交付：产品排期、设计改稿、客户项目、外包协作，以及几个人一起推进的日常工作。一块板分成几列阶段，一件事一张卡片，写上负责人、截止日期和步骤，讨论和附件留在这张卡片上，进度变了就拖到下一列。比在群里交代清楚，新消息不会把旧进度冲掉，谁在做、哪天到期始终在板上。比共享表格省事，不用改单元格来表示状态，评论和文件也不用另找地方。加人必须对方同意，只能看的人改不了板。

后端 FastAPI + SQLAlchemy 2 + MariaDB，前端是无构建步骤的原生 ES Module + CSS，没有打包器、没有 Node 依赖。

## 功能

### 按角色能做什么

四种角色，权限从高到低：`owner` > `admin` > `member` > `viewer`。项目创建者自动是 `owner`。

```mermaid
flowchart LR
    subgraph O["owner 拥有者"]
        O1["移交拥有者<br/>删除项目"]
    end
    subgraph A["admin 管理员"]
        A1["发邀请 / 撤回邀请<br/>改成员角色 / 移除成员"]
    end
    subgraph M["member 成员"]
        M1["建列表 / 建卡片<br/>编辑卡片内容<br/>拖卡片与列表排序<br/>评论 / 上传附件"]
    end
    subgraph V["viewer 只读"]
        V1["看板与卡片<br/>项目活动流"]
    end
    O1 --> A1 --> M1 --> V1
```

每级都包含下一级的全部能力。区分点：

- **owner**：唯一能移交拥有者和删除项目的角色。不能改自己的角色、不能被移除，退出项目前必须先移交。
- **admin**：管人不管内容结构——发邀请、撤回邀请、调整成员角色、移除成员。删除别人的评论和附件也需要 `admin`。
- **member**：干活的默认角色。列表、卡片、标签、清单、评论、附件都能增删改。
- **viewer**：只能读。看板、卡片详情、活动流可见，任何写操作返回 403。

### 看板与卡片

- **列表**：增删改名、改在制品上限（WIP）、拖拽排序；至少保留一个列表，删除列表时卡片会并入相邻列表。WIP 超出时只把列表计数标成强调色，服务端不阻止移动。
- **卡片**：标题、描述（Markdown）、优先级（无/低/中/高/紧急）、截止日期、封面色、完成标记、归档、复制；支持跨列与同列拖拽排序。
- **卡片详情**：标签、指派成员、清单（含勾选进度）、评论、附件、该卡片最近 30 条活动。
- **筛选**：关键词、我的、延期、标签、优先级、隐藏完成、已归档。筛选开启时禁用拖拽，避免按可见子集算出的落点错位。
- **我的任务**：跨项目汇总指派给你的卡片，`?q=` 按标题过滤。
- **活动流**：记录创建、移动、指派、评论、成员变动等 21 类动作。

### 项目与配额

新建 / 改名 / 换色 / 归档 / 恢复 / 删除 / 移交。新建成功后给创建者发一条站内通知。每人每天最多新建 `DAILY_PROJECT_LIMIT` 个项目（默认 30），按 `APP_TIMEZONE` 的自然日计算，超出返回 429。

## 技术栈

| 层 | 选型 |
| --- | --- |
| API | FastAPI（`app/main.py`），响应统一为紧凑 UTF-8 JSON |
| ORM | SQLAlchemy 2.0 + PyMySQL |
| 数据库 | MariaDB 10.11（Docker，宿主端口 3307） |
| 前端 | 原生 ES Module（`static/js/`）+ 单文件 CSS，无构建步骤 |
| 密码 | `hashlib.scrypt`（`n=2**14`） |
| 会话 | 自签名 token 存 Cookie，HMAC-SHA256 |

## 运行

数据库用仓库里的 Docker MariaDB，映射到 **3307**，不占用本机 3306。

```bash
docker compose up -d
```

Windows 下用项目虚拟环境启动（缺少 `.venv` 时会自动创建并装依赖）：

```bat
run.bat
```

或等价命令：

```bash
.venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 <http://127.0.0.1:8000>。启动时 `lifespan` 会建库（`DATABASE_URL` 里的库不存在则自动 `CREATE DATABASE`）并 `create_all` 建表，无需迁移脚本。

首次运行前复制 `.env.example` 为 `.env`；`app/config.py` 会读取 `.env`，但**不会覆盖**已存在的环境变量。

## 配置

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | `mysql+pymysql://kanban:kanban@127.0.0.1:3307/kanban?charset=utf8mb4` | 库名缺失时报错；库不存在时自动创建 |
| `SECRET_KEY` | `dev-only-change-me` | 会话签名密钥，**生产必须更换** |
| `APP_TIMEZONE` | `Asia/Shanghai` | 决定每日建项目配额的自然日边界 |
| `DAILY_PROJECT_LIMIT` | `30` | 非整数回退 30，最小 1 |
| `APP_SECURE_COOKIE` | `0` | 置 `1` 给会话 Cookie 加 `Secure`，仅在 HTTPS 下开启 |
| `SMTP_HOST` | 空 | 发注册验证码的 SMTP 主机；为空时发送接口返回 503 |
| `SMTP_PORT` | `587` | SMTP 端口 |
| `SMTP_USER` | 空 | SMTP 登录用户 |
| `SMTP_PASSWORD` | 空 | SMTP 登录口令 |
| `SMTP_FROM` | 同 `SMTP_USER` | 发件人地址 |
| `SMTP_SSL` | `0` | 置 `1` 使用隐式 SSL（常见于 465） |
| `SMTP_TLS` | `1` | 非 SSL 时是否 STARTTLS；`0` 关闭 |

## API

**写操作必须带 `X-Kanban: 1` 请求头**。`app/main.py` 的中间件会对 `POST/PUT/PATCH/DELETE` 且路径以 `/api/` 开头的请求校验该头，缺失返回 403。这是一层便宜的 CSRF 防护：浏览器表单无法伪造自定义头。前端 `static/js/api.js` 统一带上。

主要端点：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/register` `/login` `/logout` | 注册/登录/登出。注册必须带 6 位邮箱验证码 |
| POST | `/api/auth/code` | 向未注册邮箱发送验证码 |
| GET PATCH | `/api/auth/me` | 读取/更新自己的资料 |
| POST | `/api/auth/password` | 修改密码 |
| GET | `/api/bootstrap` | 一次性拿用户、项目列表、未读数、配额 |
| GET POST | `/api/projects` | 项目列表（`?archived=true` 看归档）/ 新建 |
| GET PATCH DELETE | `/api/projects/{id}` | 详情 / 修改 / 删除 |
| POST | `/api/projects/{id}/archive` `restore` `transfer` `leave` | 归档、恢复、移交、退出 |
| POST | `/api/projects/{id}/invites` | 发出邀请 |
| POST | `/api/projects/{id}/invites/{note_id}/cancel` | 撤回邀请 |
| PATCH DELETE | `/api/projects/{id}/members/{member_id}` | 改角色 / 移除成员 |
| GET | `/api/projects/{id}/activity` | 项目活动流 |
| GET | `/api/projects/{id}/board` | 整块板：项目、角色、成员、标签、列表与卡片 |
| POST | `/api/projects/{id}/columns` `cards` `labels` | 新建列表 / 卡片 / 标签 |
| POST | `/api/projects/{id}/columns/reorder` | 列表排序 |
| PATCH DELETE | `/api/columns/{id}` `/api/labels/{id}` | 改 / 删列表与标签 |
| GET PATCH DELETE | `/api/cards/{id}` | 卡片详情 / 修改 / 删除 |
| POST | `/api/cards/{id}/move` `archive` `restore` `duplicate` | 移动、归档、恢复、复制 |
| PUT | `/api/cards/{id}/labels` `assignees` | 全量替换标签 / 指派 |
| POST | `/api/cards/{id}/checklists` `comments` `attachments` | 加清单 / 评论 / 附件 |
| PATCH DELETE | `/api/checklists/{id}` `/api/checklist-items/{id}` `/api/comments/{id}` | 改删子资源 |
| GET | `/api/attachments/{id}/file` | 下载；图片扩展名自动以 inline 方式返回，其余走 attachment |
| GET | `/api/notifications` | 通知列表（最近 80 条） |
| POST | `/api/notifications/{id}/accept` `reject` `read` | 处理邀请与已读 |
| POST | `/api/notifications/read-all` | 全部标记已读 |
| GET | `/api/me/cards` | 我的任务，`?q=` 按标题过滤，上限 200 |
| GET | `/api/users/lookup` | 按邮箱查用户（找不到返回 404） |
| GET | `/api/health` | 探活，执行一次 `SELECT 1` |

## 权限模型

`ROLE_RANK` 为 `viewer 1 < member 2 < admin 3 < owner 4`，`app/services/base.py` 里统一由三个入口校验：

- `require_access`：绝大多数操作的入口。非成员一律 404（不泄露项目是否存在），角色不足 403，归档项目拒绝写（409）。
- `begin_write`：在项目行上加 `SELECT ... FOR UPDATE`，串行化同一项目的并发写。
- `_require_card`：由卡片反查项目后复用上面两条。

这三个入口在每个写操作开头调用，没有旁路。角色与能力的对应关系见上文「按角色能做什么」。

## 限额

| 项 | 上限 | 位置 |
| --- | --- | --- |
| 每日新建项目 | `DAILY_PROJECT_LIMIT`（默认 30） | `constants` / `config` |
| 每项目列表数 | 40 | `MAX_COLUMNS` |
| 每项目卡片数 | 4000 | `MAX_CARDS` |
| 每项目标签数 | 30 | `MAX_LABELS` |
| 每卡片清单数 | 20 | `MAX_CHECKLISTS` |
| 每清单条目数 | 100 | `MAX_CHECKLIST_ITEMS` |
| 每卡片评论数 | 1000 | `MAX_COMMENTS` |
| 单个附件 | 8 MB | `MAX_UPLOAD_BYTES` |

附件类型白名单见 `constants.ALLOWED_EXTENSIONS`。文件名只用于展示，落盘名是随机 hex + 原扩展名，存 `uploads/`；删除时由 `defer_unlink` 在事务提交成功后才删磁盘文件，回滚不会留下悬空引用。

接口级限流在进程内存中按来源 IP 计数（`limit.py`）：注册 10 次/小时、登录 20 次/10 分钟、邮箱查询 30 次/分钟、验证码 8 次/小时。同一邮箱 60 秒内不能重复获取验证码；验证码 10 分钟内有效，连续错 5 次作废。多实例部署时这些计数不共享，需要换成 Redis 之类的共享存储。

## 前端

单页应用，`#/` 路由解析到 `projects`、`board/{id}`、`tasks`、`notifications`、`settings`、`account` 六个视图，`hashchange` 驱动重绘。看板拖拽基于 Pointer Events：鼠标按住即拖，触屏长按 280ms 进入拖拽；筛选开启时禁用拖拽，避免按可见子集算出的落点错位。卡片详情在右侧抽屉里做乐观更新，标题、描述、截止日期失焦即保存。`Esc` 依次关闭弹层、抽屉、侧边栏。

## 测试

```bash
docker compose up -d          # 测试库由容器首次初始化时创建
.venv/Scripts/python -m pytest
```

测试库是 `kanban_test`，由 `deploy/initdb/01-test-db.sql` 建库并给 `kanban` 用户授权；`tests/conftest.py` 覆盖 `DATABASE_URL` 后每个用例前 `truncate_all()` 重建表并清空限流计数。测试用 `TestClient` 且带 `X-Kanban: 1`。

覆盖：健康检查、注册登录登出与请求头校验、注册验证码、项目与看板初始化（默认三列四标签）、邀请需批准、只读成员不能写、每日建项目上限、附件与截止日期。测试通过 `MAIL_CAPTURE=1` 截获验证码，不连真实 SMTP；生产环境不要设置这个变量。

`truncate_all()` 会 DROP 该库所有表，**不要**把 `DATABASE_URL` 指到生产库跑测试。

前端回归测试：

```bash
node --test tests/api.test.mjs tests/startup.test.mjs
```

浏览器回归为独立脚本，不由 pytest 自动收集。需要额外安装 Playwright，并通过 `CHROMIUM_PATH` 指定 Chromium 可执行文件，再运行 `python tests/startup_browser.py`。脚本只使用本地静态服务器和模拟 API，不访问数据库。

## 生产注意

- 必须换掉 `SECRET_KEY`、MariaDB 的 root 与 `kanban` 密码；`docker-compose.yml` 里是明文开发口令。
- HTTPS 下设置 `APP_SECURE_COOKIE=1`。
- 必须配置 `SMTP_HOST` 等发信变量，否则无法注册。
- 进程内限流和单 worker 假设不适配多副本；多副本时换共享存储。
- 附件写在本地磁盘，多副本或容器重建需要改成共享卷或对象存储。

## 许可证

MIT，见 [LICENSE](LICENSE)。
