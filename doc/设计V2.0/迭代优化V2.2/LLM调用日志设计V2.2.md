LLM 调用日志设计 V2.2  
更新日期：2025-12-17

## 1. 背景与目标
- 现状：LLM 调用仅有基础日志，无结构化持久化，问题定位与审计困难。
- 目标：为每次 LLM 请求/响应建立可追踪日志，支持异常排查、成本分析与提示词迭代，同时将模型调用参数（尤其温度）改为 .env 可配置。

## 2. 现状梳理（调用入口与硬编码参数）
- LLM 客户端：`infrastructure/llm/client.py#get_llm`，统一封装 `ChatOpenAI`，默认读取 `settings.LLM_MODEL`、`settings.LLM_TEMPERATURE`。
- 主要调用点：
  - `domain/router/tools/router_tools.py`: `get_llm(temperature=0.0)`（意图识别）；`get_llm(temperature=0.3)`（意图澄清）。
  - `domain/agents/factory.py`: 未指定温度时沿用 `settings.LLM_TEMPERATURE`。
- 待改造点：上述 0.0 / 0.3 需改为从 .env 注入的配置项，并保留统一默认值。

## 3. 设计原则
- **最小侵入**：在统一封装层实现日志采集，业务调用尽量少改。
- **异步友好**：兼容现有异步 SQLAlchemy 流程。
- **隐私与合规**：对用户敏感字段（手机号、邮箱）进行脱敏或按开关存储。
- **可观测性闭环**：关联请求链路（trace_id / session_id / user_id / agent_key），可快速定位问题。

## 4. 总体方案
1. **采集点**：在 LLM 调用封装层（建议在 `get_llm` 返回的模型外再包一层装饰/代理），记录请求上下文、提示词、模型参数，调用完成后记录响应与消耗。
2. **服务层**：新增 `LlmLogService`（同步/异步方法）对外暴露：
   - `start_call(...)`：写入初始行，生成 `call_id`。
   - `finish_call(call_id, ...)`：写入响应、tokens、耗时、状态。
   - `fail_call(call_id, error_code, error_message)`：异常落库。
3. **数据流**：
   - 业务调用 `chain.invoke` 前后在封装中触发 start/finish。
   - 携带上下文：user_id、session_id、agent_key、trace_id、conversation_id（从路由/会话状态读取）。
4. **配置化参数**：
   - `.env` 新增：`LLM_TEMPERATURE_DEFAULT`（保留兼容 `LLM_TEMPERATURE`）、`LLM_TEMPERATURE_INTENT`、`LLM_TEMPERATURE_CLARIFY`、`LLM_TOP_P_DEFAULT`、`LLM_MAX_TOKENS_DEFAULT`、`LLM_LOG_ENABLE`。
   - `router_tools` 中的温度改为读取 `settings.LLM_TEMPERATURE_INTENT` 与 `settings.LLM_TEMPERATURE_CLARIFY`，默认回退到 `settings.LLM_TEMPERATURE_DEFAULT`。
5. **异常与降级**：
   - 日志落库失败不影响主链路，记录到应用日志并跳过。
   - 响应内容可配置是否全量存储或截断（如 4k 字符），避免超大文本。

## 5. 数据库设计
### 5.1 表结构（至少两张表）
1) `biz_agent_llm_call_logs`（主记录）
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | BIGSERIAL PK | 主键 |
| trace_id | VARCHAR(64) | 链路追踪 ID（可与 APM 对齐） |
| session_id | VARCHAR(64) | 会话/对话标识 |
| user_id | INTEGER | 关联用户，可为空 |
| agent_key | VARCHAR(100) | 智能体标识 |
| model | VARCHAR(100) | 模型名称 |
| temperature | NUMERIC(4,2) | 实际温度 |
| top_p | NUMERIC(4,2) | 采样参数 |
| max_tokens | INTEGER | 最大输出 token |
| prompt_tokens | INTEGER | 提示消耗 |
| completion_tokens | INTEGER | 生成消耗 |
| total_tokens | INTEGER | 总消耗 |
| latency_ms | INTEGER | 耗时 |
| success | BOOLEAN | 是否成功 |
| error_code | VARCHAR(50) | 失败错误码 |
| error_message | TEXT | 失败信息 |
| created_at | TIMESTAMP | 创建时间 |
| finished_at | TIMESTAMP | 完成时间 |

2) `biz_agent_llm_call_messages`（可选分表，存储上下文与响应）
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | BIGSERIAL PK | 主键 |
| call_id | BIGINT FK | 关联 `biz_agent_llm_call_logs.id` |
| role | VARCHAR(20) | system/human/assistant/tool |
| content | TEXT | 消息内容（可截断/脱敏） |
| token_estimate | INTEGER | 估算 tokens |
| created_at | TIMESTAMP | 创建时间 |

说明：若担心体量，可只保留主表，在主表中增加 `prompt_snapshot`、`response_snapshot`（截断存储）。

## 6. 接口与组件设计
- **配置层**：在 `settings` 中新增上述 LLM 相关配置项，读取 .env。
- **模型/仓储层**：在 `infrastructure/database/models` 下新增 ORM；在 `repository` 下新增 `llm_call_log_repository.py`（含写入/更新、批量写入 message）。
- **服务层**：`infrastructure/observability/llm_logger.py`（新建模块），暴露 async 方法，内部持有 session factory，封装 try/except，保证失败不抛出到上层。
- **封装层**：为 `get_llm` 返回的模型增加代理包装（例如自定义 `LoggedChatModel`，实现 `invoke/astream` 代理），在调用前后调用 `LlmLogService`。
- **调用侧适配**：`router_tools` 和 `AgentFactory` 无需感知细节，仅通过 `get_llm` 获取已被包装的模型；必要时传入上下文（user_id、session_id、agent_key）。

## 7. 配置与硬编码整改
- 移除 `router_tools` 中的硬编码温度 0.0 / 0.3，改为：
  - 意图识别：`settings.LLM_TEMPERATURE_INTENT`（默认 0.0）。
  - 意图澄清：`settings.LLM_TEMPERATURE_CLARIFY`（默认 0.3）。
  - 均回退 `settings.LLM_TEMPERATURE_DEFAULT`（兼容旧值 `LLM_TEMPERATURE`）。
- `.env` 模板需补充新配置项，并在 `Settings` 中添加类型提示和默认值。

## 8. 迁移与兼容
- 通过 Alembic 生成迁移脚本（增表），避免破坏现有表。
- 现有调用链保持兼容，未开启日志时不写库。
- 响应内容过长时截断存储，并在日志中标记截断。

## 9. 风险与后续
- 大量日志写入导致数据库压力：可按 `LLM_LOG_ENABLE` 开关或采样率（可后续新增 `LLM_LOG_SAMPLE_RATE`）。
- 敏感数据合规：需统一脱敏策略（手机号/邮箱掩码）。
- Token 统计依赖模型返回 usage 字段，需做好空值兜底。
