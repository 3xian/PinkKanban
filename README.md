# PinkKanban

邮箱注册的多人看板。一个项目一块板，成员通过站内邀请加入：邀请发出后必须由对方在通知里批准，才会真正成为项目成员。

后端 FastAPI + SQLAlchemy 2 + MariaDB，前端是无构建步骤的原生 ES Module + CSS，没有打包器、没有 Node 依赖。

## 功能

- **项目**：新建 / 改名 / 换色 / 归档 / 恢复 / 删除 / 移交拥有者。每人每天最多新建 `DAILY_PROJECT_LIMIT` 个项目（默认 30），按 `APP_TIMEZONE` 的自然日计算。
- **成员与角色**：`owner` > `admin` > `member` > `viewer`。只读成员能看不能写；邀请、改角色、移人需要 `admin`；移交和删除项目需要 `owner`。
- **看板**：列表增删、改名、改在制品上限（WIP）、拖拽排序；至少保留一个列表。WIP 超出只在列表头标红提示，服务端不阻止移动。
- **卡片**：标题、描述（Markdown）、优先级、截止日期、封面色、完成标记、归档、复制、跨列与同列拖拽排序。
- **卡片详情**：标签、指派成员、清单（含勾选进度）、评论、附件、该卡片最近 30 条活动。
- **邀请与通知**：邀请以通知形式投递，接收方接受或拒绝；另有 `@提及`、指派、评论、项目移交等通知类型。
- **筛选与「我的任务」**：按关键词、我的、逾期、标签、优先级、隐藏完成、已归档筛选卡片；另有跨项目的「我的任务」视图。
- **项目活动流**：记录创建、移动、指派、评论、成员变动等 21 类动作。

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

## 目录结构

```
app/
  main.py        应用装配、CSRF 中间件、安全响应头、SPA 回退、/api/health
  config.py      .env 读取与配置访问器
  db.py          engine / session / 建库建表 / 提交后删文件
  models.py      15 张表的 SQLAlchemy 模型
  schemas.py     Pydantic 入参与清洗（邮箱小写、名称截断与去空白）
  services.py    全部业务规则与权限校验
  routers/       auth、projects、board、inbox
  security.py    scrypt 口令、会话签名
  limit.py       进程内滑动窗口限流
  constants.py   角色、优先级、配色、各类上限
static/
  index.html     单页入口
  js/app.js      状态机与所有视图
  js/dnd.js      Pointer Events 拖拽（鼠标直接拖，触屏长按 280ms）
  js/format.js   时间、Markdown、头像等展示工具
tests/           pytest，跑在 kanban_test 库
deploy/initdb/   容器首次初始化时创建测试库并授权
uploads/         附件落盘目录（内容已 gitignore）
```

## API

**写操作必须带 `X-Kanban: 1` 请求头**。`app/main.py` 的中间件会对 `POST/PUT/PATCH/DELETE` 且路径以 `/api/` 开头的请求校验该头，缺失返回 403。这是一层便宜的 CSRF 防护：浏览器表单无法伪造自定义头。前端 `static/js/api.js` 统一带上。

主要端点：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/register` `/login` `/logout` | 注册/登录/登出 |
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

`ROLE_RANK` 为 `viewer 1 < member 2 < admin 3 < owner 4`，`services.py` 里统一由三个入口校验：

- `require_access`：非成员一律 404（不泄露项目是否存在），角色不足 403，归档项目拒绝写（409）。
- `begin_write`：在项目行上加 `SELECT ... FOR UPDATE`，串行化同一项目的并发写。
- `_require_card`：由卡片反查项目后复用上面两条。

写操作默认要求 `member` 及以上；邀请/角色/移除成员要求 `admin`；移交与删除要求 `owner`。评论和附件只能改删自己的，`admin` 及以上例外。拥有者不能改自己角色、不能被移除、退出前需先移交。

## 限额

| 项 | 上限 | 位置 |
| --- | --- | --- |
| 每日新建项目 | `DAILY_PROJECT_LIMIT`（默认 30） | `constants` / `config` |
| 每项目列表数 | 40 | `MAX_COLUMNS` |
| 每项目卡片数 | 4000 | `MAX_CARDS` |
| 每项目标签数 | 30 | `services.create_label` |
| 每卡片清单数 | 20 | `services.create_checklist` |
| 每清单条目数 | 100 | `services.add_item` |
| 每卡片评论数 | 1000 | `services.add_comment` |
| 单个附件 | 8 MB | `MAX_UPLOAD_BYTES` |

附件类型白名单见 `constants.ALLOWED_EXTENSIONS`。文件名只用于展示，落盘名是随机 hex + 原扩展名，存 `uploads/`；删除时由 `defer_unlink` 在事务提交成功后才删磁盘文件，回滚不会留下悬空引用。

接口级限流在进程内存中按来源 IP 计数（`limit.py`）：注册 10 次/小时、登录 20 次/10 分钟、邮箱查询 30 次/分钟。多实例部署时这些计数不共享，需要换成 Redis 之类的共享存储。

## 前端

单页应用，`#/` 路由解析到 `projects`、`board/{id}`、`tasks`、`notifications`、`settings`、`account` 六个视图，`hashchange` 驱动重绘。看板拖拽基于 Pointer Events：鼠标按住即拖，触屏长按 280ms 进入拖拽；筛选开启时禁用拖拽，避免按可见子集算出的落点错位。卡片详情在右侧抽屉里做乐观更新，标题、描述、截止日期失焦即保存。`Esc` 依次关闭弹层、抽屉、侧边栏。

## 测试

```bash
docker compose up -d          # 测试库由容器首次初始化时创建
.venv/Scripts/python -m pytest
```

测试库是 `kanban_test`，由 `deploy/initdb/01-test-db.sql` 建库并给 `kanban` 用户授权；`tests/conftest.py` 覆盖 `DATABASE_URL` 后每个用例前 `truncate_all()` 重建表并清空限流计数。测试用 `TestClient` 且带 `X-Kanban: 1`。

覆盖：健康检查、注册登录登出与请求头校验、项目与看板初始化（默认三列四标签）、邀请需批准、只读成员不能写、每日建项目上限、附件与截止日期。

`truncate_all()` 会 DROP 该库所有表，**不要**把 `DATABASE_URL` 指到生产库跑测试。

## 生产注意

- 必须换掉 `SECRET_KEY`、MariaDB 的 root 与 `kanban` 密码；`docker-compose.yml` 里是明文开发口令。
- HTTPS 下设置 `APP_SECURE_COOKIE=1`。
- 进程内限流和单 worker 假设不适配多副本；多副本时换共享存储。
- 附件写在本地磁盘，多副本或容器重建需要改成共享卷或对象存储。

## 许可证

MIT，见 [LICENSE](LICENSE)。
