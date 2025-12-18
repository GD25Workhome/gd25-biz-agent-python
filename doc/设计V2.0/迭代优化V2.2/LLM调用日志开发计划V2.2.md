LLM 调用日志开发计划 V2.2  
更新日期：2025-12-17

## 1. 范围与目标
- 建立 LLM 请求/响应结构化日志表，支持链路追踪、异常排查与成本统计。
- 将 LLM 温度等关键参数改为 .env 可配置，消除业务硬编码。

## 2. 需求拆解
1) **配置改造**
   - `settings` 新增：`LLM_TEMPERATURE_DEFAULT`（兼容旧 `LLM_TEMPERATURE`）、`LLM_TEMPERATURE_INTENT`、`LLM_TEMPERATURE_CLARIFY`、`LLM_TOP_P_DEFAULT`、`LLM_MAX_TOKENS_DEFAULT`、`LLM_LOG_ENABLE`。
   - `.env.example` / `.env` 增补示例与注释。
   - `router_tools` 温度读取改为上述配置（移除 0.0 / 0.3 硬编码）。
2) **数据层**
   - 在 `infrastructure/database/models` 增加 `biz_agent_llm_call_logs`、`biz_agent_llm_call_messages` ORM。
   - 在 `repository` 新增 `llm_call_log_repository.py`，提供 start/finish/fail、批量写入消息接口。
   - 编写 Alembic 迁移脚本，创建两张表（含索引：trace_id、session_id、agent_key、created_at）。
3) **服务与封装**
   - 新建 `infrastructure/observability/llm_logger.py`，提供异步 `start_call/finish_call/fail_call`，失败不抛出。
   - 在 `get_llm` 外层增加代理/装饰器（或封装 `LoggedChatModel`），在 `invoke/astream` 前后调用日志服务，并收集 usage 与耗时。
   - 为代理注入上下文（user_id、session_id、agent_key、trace_id、conversation_id），从路由/状态机读取并透传。
4) **业务接入**
   - `router_tools`、`AgentFactory` 使用包装后的 llm（无需手动记录日志）。
   - 若需要工具级透传，提供可选上下文参数。
5) **测试**
   - 单元测试：日志服务写入/更新、异常兜底、参数默认值回退。
   - 集成测试：模拟一次意图识别/澄清流程，断言日志表写入成功、温度来源为配置。
6) **文档**
   - 更新设计与开发文档（本次新增已覆盖），补充 `.env` 配置说明、迁移使用指引。
7) **上线与回滚**
   - 上线步骤：执行 Alembic 迁移 → 部署应用 → 验证采样日志。
   - 回滚策略：禁用 `LLM_LOG_ENABLE` 或回滚迁移脚本。

## 3. 里程碑与时间预估（工作日）
- M1：配置改造与迁移脚本（1d）
- M2：日志服务与模型代理实现（1.5d）
- M3：业务接入与测试（1d）
- M4：文档收尾与上线验收（0.5d）

## 4. 验收标准
- 新表成功创建，索引生效；`LLM_LOG_ENABLE=true` 时能看到完整日志数据。
- `router_tools` 温度取自 .env 配置，默认回退逻辑生效。
- 单元/集成测试通过；日志写入失败不影响主流程。
- 文档与示例配置齐全，可指导后续迭代。
