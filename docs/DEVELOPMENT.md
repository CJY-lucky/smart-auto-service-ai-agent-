# 开发说明

这份文档说明 `smart-auto-service-ai-agent` 的落地实现：怎么跑起来、各部分负责什么、
哪些地方做了取舍。设计初衷见根目录 `README.md`。

## 1. 五分钟跑起来

```powershell
cd C:\桌面\smart-auto-service-ai-agent

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt

Copy-Item .env.example .env
# 编辑 .env，至少填写 LLM_API_KEY（DeepSeek 平台获取）

python -m scripts.seed_demo          # 可选：生成演示用的车主与车辆档案
python -m uvicorn app:app --reload --port 8000
```

打开 http://127.0.0.1:8000 就能对话预约，`/docs` 是接口文档，`/schedule` 是车间排班看板。

### 关于模型配置

| 配置项 | 说明 |
| --- | --- |
| `MODEL_PROVIDER=deepseek` | 聊天模型走 DeepSeek 的 OpenAI 兼容接口 |
| `LLM_BASE_URL=https://api.deepseek.com/v1` | DeepSeek 兼容接口地址 |
| `LLM_MODEL=deepseek-chat` | 对话模型；需要更强推理可换 `deepseek-reasoner` |
| `EMBEDDING_PROVIDER=local` | DeepSeek 不提供通用 Embedding，默认走本地确定性向量，零密钥可跑 |

`EMBEDDING_PROVIDER` 也可以换成 `qwen`（百炼 `text-embedding-v3`）、`zhipu`（`embedding-3`）、
`openai`（`text-embedding-3-small`）。换了向量模型后知识库会自动重建索引，不需要手工清库。

**没有 API Key 也能跑。** 未配置 `LLM_API_KEY` 时系统不会崩溃，也不会编造调用，
而是自动切到规则兜底模式：意图分类走关键词打分、预约信息走正则解析、咨询回答直接用检索到的知识原文。
这让本地开发、单元测试和演示环境都不依赖外网。

## 2. 分层与调用方向

```text
Web 层   web/        页面与静态资源，只做渲染，数据全部通过 API 获取
  ↓
API 层   api/        接口编排、参数校验、响应封装
  ↓
Agents   agents/     多 Agent 协作、任务路由、对话流程
  ↓
Services services/   业务逻辑：排班、工单、知识库、行为分析（唯一做业务判断的地方）
  ↓
DB 层    db/         模型、会话、Repository
```

硬性规则：下层不能反向调用上层；Agents 不能绕过 Services 直接操作数据库；
所有 SQL 只出现在 `db/repositories/`。

## 3. 核心实现要点

### 3.1 双资源排班（`services/scheduling_service.py`）

一次预约要同时满足：一名具备资质的技师 + 类型匹配的空闲工位。做法是：

1. `estimate_workload()` 把项目清单整理成**工序**：按 `depends_on` 做拓扑排序
   （例如四轮定位必须在换胎之后），累加工时；相邻工序若没有可共用的工位类型，
   自动加 5 分钟工位转移时间。
2. `find_solution()` 先筛技师（资质 + 班次 + 整段空闲），再为每道工序分配工位
   （只在该工序的时间片段上判断占用）。
3. 任何一个环节不满足，返回结构化的失败原因（`ConflictReason`）与**备选时段**，
   由 Agent 翻译成车主能听懂的话。

技师占整段时间、工位按工序分段，是因为技师不可能同时出现在两个工位，
而车辆可以在工序之间挪到别的工位。工单表用 `bay_plan` 字段记录分段计划
（`[{item_code, bay_id, bay_name, bay_type, start, end}]`），
后续判断工位占用时按分段展开，而不是简单地看主工位。

### 3.2 大模型只负责"听懂"（`agents/`）

- `InputParser`：把口语翻译成结构化字段（车牌、车型、里程、时间、项目、偏好、指定技师）。
  有模型时输出 JSON 并做容错解析，没有模型时用正则与项目词典兜底。
- `SchedulingService`：负责"能不能排上、排在哪"。
- 模型理解出现偏差时，最坏结果只是排期失败或追问一次，不会排出车间里做不到的工单。

### 3.3 咨询的安全性（`agents/consultant/`）

保养问题涉及行车安全，所以：回答必须基于知识库；知识库没有的就说没有并建议致电；
仪表盘红灯、刹车异常这类问题，回答前先插入明确的安全提示（停车、不要继续行驶、尽快到店）。

检索用"FAISS 向量召回 + 门店关键词命中加权"的混合方式，
中文短句下比纯向量稳定得多（问价格就能召回价格条目）。

### 3.4 车辆档案与周期推理（`services/vehicle_service.py`）

按里程与时间双维度比对每个项目的周期（`config/service_catalog.py` 定义），
到达周期的 90% 就提醒，留出预约缓冲。工单完成后回写 `last_service_date` 与里程，
所以"提醒"依据的是这辆车的真实使用情况，而不是所有人都推同一套套餐。

### 3.5 并发与数据一致性

SQLite 没有行级锁，"检查空闲 → 写入工单"之间存在竞态。
`services/work_order_service.py` 在写入临界区（`db/base/locks.py` 的进程内锁）里
**二次校验**技师与工位，避免并发请求排出互相冲突的两张工单。
真实多实例部署时应把这一步换成数据库唯一约束或悲观锁。

### 3.6 时间口径

全系统统一用"北京时间 + naive datetime"，时间窗一律按半开区间 `[start, end)` 处理
（首尾相接不算冲突），营业时间 9:00-20:00、排期粒度 30 分钟、班次定义都收敛在
`config/time_config.py`，其它模块不许自己写死小时数。

### 3.7 Embedding 缓存

`services/text_embedding.py` 做两级缓存（进程内存 + `embedding_cache` 表），
同一段文本只调用一次向量接口；换向量模型时会因为缓存键包含模型名而自动失效。

## 4. 目录速览

```text
app.py                     应用入口（启动时初始化知识库/技师/工位，按需启动提醒调度）
config/                    常量、设置、时间基准、模型工厂、服务目录
db/                        模型、会话、并发锁、Repository
services/                  排班、工单、技师、工位、车辆、知识库、行为分析、提醒调度
agents/                    任务分类 / 预约工单 / 咨询 / 车主行为 四个 Agent
api/                       对外接口（含确定性排班接口，可脱离大模型直接调用）
web/                       页面与静态资源
scripts/seed_demo.py       演示数据
tests/                     单元测试与接口测试
mcp_server/                可选的 MCP 天气服务（默认不使用，见文件说明）
```

## 5. 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

测试完全离线：`tests/conftest.py` 会把数据库指向临时文件并关闭模型调用。
覆盖的重点是**排班的确定性行为**（占用冲突、首尾相接不算冲突、资质校验、
跨工位工序、备选时段、并发下单防护、档案回写），以及意图分类、RAG 检索与安全兜底。

## 6. 常用接口

| 接口 | 用途 |
| --- | --- |
| `POST /api/task/classify` | 判断这句话属于预约/咨询/档案/行为/无关 |
| `POST /api/service-booking/quote` | 试算工时、金额、可行性、备选时段（不落库） |
| `POST /api/service-booking/orders` | 创建工单 |
| `POST /api/service-booking/orders/{id}/reschedule` | 改约 |
| `POST /api/service-booking/orders/{id}/cancel` | 取消 |
| `POST /api/service-booking/orders/{id}/complete` | 完工，并回写车辆档案 |
| `GET /api/service-booking/board?day=YYYY-MM-DD` | 排班看板数据 |
| `POST /api/consultation/ask` | 咨询问答 |
| `GET/POST /api/knowledge` | 知识库维护 |
| `GET /api/vehicles/{id}` | 车辆档案 + 到期项目 + 下次保养推算 |
| `GET /api/vehicle-behavior/analysis` | 车主行为分析 |
| `POST /api/vehicle-behavior/send-reminder` | 生成带可约时段的回访提醒 |
| `POST /chat/stream` | 流式对话（前端使用，token 带 `[THOUGHT]`/`[REPLY]` 标记） |

## 7. 已知取舍与后续方向

- **单门店、单进程**：会话状态放在进程内存里，多门店/多用户需要把 Agent 实例按 session 缓存，
  并把并发锁换成数据库级约束。
- **排班是贪心匹配**：按"第一个满足条件的技师 + 工位"落单，还没有做全局最优；
  后续可以换成带约束的求解（时间窗、项目依赖、倒班、工位利用率一起优化）。
- **天气接入是可选项**：配置 `OPENWEATHER_API_KEY` 后会给预约成功消息和提醒加上用车提示，
  未配置则跳过，不影响主流程。`mcp_server/` 里提供了一个可选的 MCP 版本。
- **前端是轻量页面**：Jinja2 模板 + 原生 JS，够用但没做组件化；
  需要更复杂的交互时可以换成前端框架，接口不需要动。