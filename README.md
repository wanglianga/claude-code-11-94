# 退役电池包收货与安全放行系统

面向拆解中心的收货、隔离、拆解、检测、安全放行、仓库拣货与下游签收一体化应用。
技术栈：**Vue 3 + Vite（前端）**、**FastAPI + SQLAlchemy（后端）**、**PostgreSQL（数据库）**。

---

## 1. 业务能力与规则落地

| 需求点 | 实现位置/行为 |
| --- | --- |
| 每包唯一序列号；重复扫码只返回原收货单 | `services/receiving.py::receive_pack`，响应字段 `duplicated=true` |
| 收货单显示隔离位、责任班组、未完成前置项 | 收货单与包列表均返回 `pending_preconditions`（碰撞/浸水未复检、热事件未结案、缺隔离位/班组） |
| 整批隔离 vs 单包隔离 | `freeze_batch` / `quarantine_pack`；整批冻结挡住同车所有包，单包隔离仅冻结风险包 |
| 双方见证扫码建立包→模组父子关系 | `services/dismantling.py::link_module`，两名见证者必须不同 |
| 重贴标签保留旧号、操作者、时间，两人分别确认 | `label_history` 表 + `relabel` 两阶段接口（发起→第二人确认生效） |
| 无法确认父子关系的模组隔离待核 | `register_unknown_module`：`pack_id=NULL、unknown_parent=true`，工单挂起，**绝不自动归到最相似序列号** |
| BMS 正常不能抵消碰撞/浸水历史 | `services/safety.py::echelon_blockers` 明确提示该原则，必须有复检合格回执 |
| 校准过期 / 绝缘失败 / 热事件未结案禁止梯次利用 | 同上函数的硬门禁，任一命中即 409 拒绝 |
| 8 种状态互不混淆 | `enums.PackStatus`：接收、隔离、拆解、待检、待审批、可复用、待回收、已出库 |
| 退回补检后旧放行单失效 | `_void_active_approvals`：旧单 `voided`，待拣货单 `corrected`，已通知买家收到更正通知 |
| 仓库只能按已批准去向拣货 | `warehouse.pick` 校验放行单有效性并沿父子链重新校验 |
| 出库单限数量、用途、收货人 | 梯次利用批准时自动生成 `outbound_orders`，超限量出库被拒绝 |
| 买家拒收只能退回隔离待复核 | `sign_off(rejected)`：包回到 `quarantined+frozen`，不自动回可用库存 |
| 装车货物不能删除，只能召回/退运 | `recall_or_return`，历史出库单与审计日志保留 |
| 数量核对：放行/拆出/称重/已发差额未解释阻止结清 | `compute_reconciliation` + `close_batch`（409 `reconciliation_blocked`） |
| 单包策略下每次拆分/换标/出库沿父子链重校验 | `revalidate_parent_chain` 在拣货、装车前强制执行 |
| 全链路留痕 | `audit_logs` 表 + `/api/audit/logs` |

### 样例 L-7（种子数据自动播种）

- **P-1**：碰撞记录（COL-2026-001）且未复检；**P-2 / P-3 / P-4**：身份链完整、检测合格、无共同热事件。
- 前端「L-7 场景」页或 `POST /api/scenario/l7/compare` 可对比两种策略（仿真在独立事务中回滚，不污染真实数据）：
  - 整批冻结：P-1~P-4 全部不可放行，待拣货单 0、买家通知 0；
  - 单包隔离：P-2/P-3/P-4 先放行（3 张拣货单、3 条买家通知）；P-3 收到迟到浸水回执后仅暂停 P-3，旧放行单失效、拣货单更正、买家收更正通知，P-2/P-4 继续流转；P-1 拆解发现失配重贴标签 → 模组 `M-UNKNOWN-9` 隔离待核、工单挂起。

---

## 2. 测试账号（种子数据，无密码，登录后请求自动带 `X-Username` 头）

| 账号 | 姓名 | 角色 | 班组 |
| --- | --- | --- | --- |
| `u_receiver` | 王接收 | 接收员 receiver | 收货一班 |
| `u_dismantler` | 李拆解 | 拆解员 dismantler | 拆解一班 |
| `u_dismantler2` | 赵拆解 | 拆解员 dismantler（双见证/换标第二人） | 拆解二班 |
| `u_safety` | 陈安全 | 安全工程师 safety | 安全工程组 |
| `u_warehouse` | 孙仓储 | 仓库 warehouse | 仓储班 |
| `u_downstream` | 周买家 | 下游买家 downstream | 华东储能公司 |
| `u_admin` | 管理员 | 中心管理员 admin | 中心管理组 |

种子检测设备：`DEV-OK`（校准有效 1 年）、`DEV-EXPIRED`（校准已过期 30 天，用于验证门禁）。

---

## 3. 一键启动（Docker Compose）

```bash
cd /workspace/94
docker compose up --build
```

- 前端：http://localhost:8080
- 后端 API：http://localhost:8000
- 交互式 API 文档（Swagger UI）：http://localhost:8000/docs
- 首次启动自动建表并播种 L-7 场景数据。

---

## 4. 本地开发启动（容器内预装运行时方式）

### 4.1 后端

```bash
cd backend
/opt/python-3.12/bin/python3 -m venv .venv
.venv/bin/pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
# 数据库指向本机 PostgreSQL（预装库 ccdev，或自建 battery_demo）
export DATABASE_URL="postgresql+psycopg2://ccdev:ccdev@127.0.0.1:5432/battery_demo"
.venv/bin/uvicorn app.main:app --reload --port 8000
```

服务启动时自动 `create_all` 建表并播种；Swagger UI：http://127.0.0.1:8000/docs。

### 4.2 前端

```bash
cd frontend
/opt/node-22/bin/npm install --registry=https://registry.npmmirror.com --cache=./.npm-cache
/opt/node-22/bin/npm run dev      # http://127.0.0.1:5173 ，/api 已代理到 8000
# 生产构建/预览
/opt/node-22/bin/npm run build && /opt/node-22/bin/npm run preview   # http://127.0.0.1:8080
```

---

## 5. 验证方式

### 5.1 自动化测试（27 个用例）

```bash
cd backend
# 先建测试库：psql -h 127.0.0.1 -U ccdev -d ccdev -c "CREATE DATABASE battery_test;"
DATABASE_URL="postgresql+psycopg2://ccdev:ccdev@127.0.0.1:5432/battery_test" \
  .venv/bin/python -m pytest tests/ -v
```

覆盖：重复扫码、收货单前置项、整批/单包隔离、出库包只能召回、角色鉴权、双见证、同人见证拒绝、未知模组隔离与工单挂起、换标两人确认与留痕、碰撞/浸水 BMS 不可抵消、复检解除、校准过期、绝缘失败、热事件结案、退回补检失效与下游更正、拒收回隔离、召回退运、数量核对阻截结清、L-7 双策略对比与回滚无污染。

### 5.2 L-7 命令行演示

```bash
DATABASE_URL="postgresql+psycopg2://ccdev:ccdev@127.0.0.1:5432/battery_demo" \
  .venv/bin/python demo_l7.py
```

### 5.3 界面手工验证路径

1. 用 `u_receiver` 登录，在「收货/隔离」页扫码收一包并再次扫同一序列号 → 提示返回原收货单；
2. 「L-7 场景」页点击运行仿真，对比两种策略的可放行包、待拣货单、买家通知；
3. 切 `u_safety`：查看 P-1 门禁（碰撞未复检）→ 对 P-2 批准梯次利用（自动生成出库单与买家通知）；
4. 切 `u_warehouse`：拣货 → 装车；切 `u_downstream`：拒收 → 回「收货/隔离」确认包回到隔离冻结；
5. 「仓库/核对」页对 L-7 尝试结清 → 存在差额时被阻止，填写解释后可结清。

---

## 6. 实际执行过的验证结论（本工作区）

- ✅ `pytest tests/`：**27 passed**（PostgreSQL `battery_test` 库，真实 PG 18 而非 SQLite）。
- ✅ `demo_l7.py`：整批冻结可放行 `[]`、拣货单 0、通知 0；单包隔离初始放行 `['P-2','P-3','P-4']`、拣货单 3、通知 3；P-3 迟到浸水后拣货 `blocked`、更正通知 1 条、P-2/P-4 继续流转；P-1 失配模组 `M-UNKNOWN-9` 为 `quarantine_review` 且 `pack_id=None`，工单关闭被阻止。
- ✅ HTTP 端到端抽验（uvicorn 实跑）：登录、重复扫码、P-1 门禁拦截、P-2 批准→拣货→装车全链路、L-7 仿真接口、仿真回滚后真实 P-3 仍为 `pending_approval`（无污染）。
- ✅ 前端 `npm run build` 构建成功；`vite preview`（8080）与 `vite dev`（5173）均 HTTP 200，`/api` 代理到后端正常。
- ⚠️ 当前容器未安装 docker CLI，`docker compose up --build` 配置已交付但**未在本容器内实际执行**；在具备 Docker 的环境中可直接一键启动。

---

## 7. 目录结构

```
94/
├── docker-compose.yml          # 一键启动 db + backend + frontend
├── backend/
│   ├── Dockerfile / entrypoint.sh
│   ├── requirements.txt
│   ├── demo_l7.py              # L-7 命令行演示
│   ├── app/
│   │   ├── main.py             # FastAPI 入口（异常处理/CORS/建表播种）
│   │   ├── models.py           # SQLAlchemy 模型
│   │   ├── enums.py            # 8 种包状态等枚举
│   │   ├── seed.py             # 账号/设备/L-7 种子
│   │   ├── services/           # 业务规则（收货、拆解、安全放行、仓库、L-7 仿真）
│   │   └── routers/            # API 路由
│   └── tests/                  # pytest 27 例
└── frontend/
    ├── Dockerfile / nginx.conf
    └── src/views/              # 收货、拆解、检测台、安全审批、仓库、下游签收、L-7、审计
```
