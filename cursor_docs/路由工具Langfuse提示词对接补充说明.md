# 路由工具Langfuse提示词对接补充说明

## 背景

在阶段一的Langfuse提示词模版对接中，最初只处理了功能型Agent（blood_pressure_agent、appointment_agent等），但遗漏了路由系统中的两个重要工具：
1. **意图识别工具**（`identify_intent`）
2. **意图澄清工具**（`clarify_intent`）

这两个工具虽然不是独立的Agent，但同样使用提示词，也应该迁移到Langfuse进行管理。

## 改造内容

### 1. 代码改造

#### 1.1 更新 `domain/router/tools/router_tools.py`

**意图识别工具（`identify_intent`）**：
- 支持从Langfuse加载提示词（模版名称：`router_intent_identification_prompt`）
- 加载优先级：Langfuse > PromptManager > Fallback
- 支持占位符填充（系统占位符 + 运行时占位符：query, history, current_intent）

**意图澄清工具（`clarify_intent`）**：
- 支持从Langfuse加载提示词（模版名称：`router_clarify_intent_prompt`）
- 加载优先级：Langfuse > PromptManager > Fallback
- 支持占位符填充（系统占位符 + 运行时占位符：query）

### 2. 提示词内容更新

#### 2.1 意图识别提示词

**文件**: `config/prompts/modules/router/intent_identification.txt`

**更新内容**：
- 从原来的2个意图类型（blood_pressure, appointment）扩展为5个意图类型
- 新增：health_event、medication、symptom
- 更新优先级规则：appointment > health_event > medication > symptom > blood_pressure

#### 2.2 意图澄清提示词

**文件**: `config/prompts/modules/router/clarify_intent.txt`

**更新内容**：
- 从原来的2个功能扩展为5个功能
- 新增：记录健康事件、记录用药、记录症状
- 更新字数限制：从100字增加到150字

### 3. Langfuse模版配置

#### 3.1 模版清单

需要在Langfuse平台创建以下2个路由工具提示词模版：

| 模版名称 | 用途 | 占位符 |
|---------|------|--------|
| `router_intent_identification_prompt` | 路由意图识别 | user_id, session_id, current_date, query, history, current_intent |
| `router_clarify_intent_prompt` | 路由意图澄清 | user_id, session_id, current_date, query |

#### 3.2 配置说明

**重要**：路由工具提示词**不需要**在`config/agents.yaml`中配置，因为：
- 路由工具不是独立的Agent
- 代码中直接使用模版名称从Langfuse加载
- 加载逻辑已集成到`router_tools.py`中

### 4. 测试验证

#### 4.1 新增测试用例

在`cursor_test/M3_test/langfuse/test_langfuse_prompts_loading.py`中新增：
- `test_router_tools_prompts()`: 验证路由工具提示词配置和降级文件存在

#### 4.2 更新测试用例

- `test_load_prompts_from_langfuse()`: 扩展为包含路由工具提示词的测试

#### 4.3 测试结果

所有7个测试用例全部通过：
- ✅ test_all_agents_have_langfuse_template_config
- ✅ test_router_tools_prompts（新增）
- ✅ test_langfuse_template_names
- ✅ test_load_prompts_from_langfuse（已更新）
- ✅ test_placeholder_configuration
- ✅ test_fallback_configuration
- ✅ test_template_version_configuration

## 完整提示词清单

### 所有需要创建的Langfuse模版（共7个）

| # | 模版名称 | 类型 | 用途 |
|---|---------|------|------|
| 1 | `blood_pressure_agent_prompt` | Agent | 血压记录智能体 |
| 2 | `appointment_agent_prompt` | Agent | 复诊管理智能体 |
| 3 | `health_event_agent_prompt` | Agent | 健康事件记录智能体 |
| 4 | `medication_agent_prompt` | Agent | 用药记录智能体 |
| 5 | `symptom_agent_prompt` | Agent | 症状记录智能体 |
| 6 | `router_intent_identification_prompt` | 路由工具 | 路由意图识别 |
| 7 | `router_clarify_intent_prompt` | 路由工具 | 路由意图澄清 |

## 使用方式

### 代码使用

路由工具会自动从Langfuse加载提示词（如果配置了Langfuse）：

```python
# 意图识别工具
from domain.router.tools.router_tools import identify_intent

result = identify_intent(messages)
# 内部会自动从Langfuse加载 router_intent_identification_prompt

# 意图澄清工具
from domain.router.tools.router_tools import clarify_intent

clarification = clarify_intent(query)
# 内部会自动从Langfuse加载 router_clarify_intent_prompt
```

### 配置要求

1. **环境变量**（`.env`）：
   ```env
   LANGFUSE_ENABLED=true
   LANGFUSE_PUBLIC_KEY=pk-xxx
   LANGFUSE_SECRET_KEY=sk-xxx
   LANGFUSE_HOST=https://cloud.langfuse.com
   PROMPT_USE_LANGFUSE=true
   ```

2. **Langfuse平台**：
   - 创建7个提示词模版（包括2个路由工具模版）
   - 设置版本号（可选，如`v1.0`）

3. **配置文件**：
   - Agent提示词：在`config/agents.yaml`中配置`langfuse_template`
   - 路由工具提示词：无需配置，代码自动处理

## 降级机制

如果Langfuse不可用，路由工具会自动降级：
1. 首先尝试从Langfuse加载
2. 如果失败，尝试从PromptManager加载（使用本地文件）
3. 如果都失败，使用代码中的Fallback提示词

## 注意事项

1. **路由工具不是Agent**：路由工具是路由系统的一部分，不是独立的Agent
2. **无需配置**：路由工具提示词不需要在`agents.yaml`中配置
3. **占位符支持**：路由工具提示词支持系统占位符和运行时占位符
4. **版本管理**：建议在Langfuse中为路由工具提示词创建版本，便于回滚

## 完成状态

- ✅ 代码改造完成
- ✅ 提示词内容更新完成
- ✅ 测试用例完成并通过
- ✅ 文档更新完成
- ⏳ 等待手动上传到Langfuse平台

