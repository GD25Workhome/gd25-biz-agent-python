# 阶段三Agent生命周期管理与阶段四测试文档开发总结

## 文档说明

本文档总结了V4.1开发方案中阶段三（Agent生命周期管理）和阶段四（测试与文档）的开发内容。

**文档版本**：V1.0  
**创建时间**：2025-01-XX  
**开发阶段**：V4.1 Agent优化+Langfuse接入

---

## 目录

1. [阶段三：Agent生命周期管理](#阶段三agent生命周期管理)
2. [阶段四：测试与文档](#阶段四测试与文档)
3. [开发指南](#开发指南)
4. [配置说明](#配置说明)
5. [API接口说明](#api接口说明)

---

## 阶段三：Agent生命周期管理

### 3.1 Agent缓存机制

#### 3.1.1 实现内容

在 `AgentFactory` 中实现了完整的Agent缓存机制：

**核心功能**：
- **Agent缓存**：创建的Agent实例会被缓存，避免重复创建
- **配置更新检测**：自动检测配置文件（`agents.yaml`）的修改时间，更新时自动清除缓存
- **缓存清理**：支持清除单个Agent缓存或所有缓存
- **缓存统计**：提供缓存命中率、缓存大小等统计信息

**实现位置**：`domain/agents/factory.py`

**关键代码**：
```python
# Agent缓存字典
_agent_cache: Dict[str, CompiledGraph] = {}

# 配置文件修改时间跟踪
_config_mtime: Optional[float] = None

# 线程锁（保证线程安全）
_cache_lock = threading.Lock()

# 缓存统计
_cache_stats: Dict[str, Any] = {
    "hits": 0,
    "misses": 0,
    "created": 0,
    "reloaded": 0,
    "cleared": 0,
}
```

#### 3.1.2 使用方法

**创建Agent（自动缓存）**：
```python
from domain.agents.factory import AgentFactory

# 第一次创建（缓存未命中，会创建并缓存）
agent1 = AgentFactory.create_agent("blood_pressure_agent")

# 第二次创建（缓存命中，直接返回缓存的实例）
agent2 = AgentFactory.create_agent("blood_pressure_agent")

# agent1 和 agent2 是同一个实例
assert agent1 is agent2
```

**强制重新加载**：
```python
# 强制重新加载（忽略缓存）
agent = AgentFactory.create_agent("blood_pressure_agent", force_reload=True)
```

**清除缓存**：
```python
# 清除单个Agent缓存
AgentFactory.clear_cache("blood_pressure_agent")

# 清除所有缓存
AgentFactory.clear_cache()
```

**获取缓存统计**：
```python
stats = AgentFactory.get_cache_stats()
print(f"缓存命中率: {stats['hit_rate']:.2%}")
print(f"缓存大小: {stats['cache_size']}")
print(f"缓存的Agent: {stats['cached_agents']}")
```

**检查是否已缓存**：
```python
if AgentFactory.is_cached("blood_pressure_agent"):
    print("Agent已缓存")
```

#### 3.1.3 配置更新检测

系统会自动检测配置文件（`agents.yaml`）的修改时间：

- **自动检测**：每次调用 `create_agent()` 或 `load_config()` 时自动检测
- **自动清除**：检测到配置更新时，自动清除所有Agent缓存
- **无需手动操作**：配置更新后，下次创建Agent时会自动使用新配置

**工作原理**：
1. 首次加载配置时，记录配置文件的修改时间（`mtime`）
2. 每次创建Agent前，检查配置文件的当前修改时间
3. 如果当前修改时间 > 记录的修改时间，说明配置已更新
4. 自动清除所有缓存，确保使用最新配置

### 3.2 Agent热更新

#### 3.2.1 实现内容

实现了Agent热更新功能，支持在不重启应用的情况下重新加载Agent：

**核心功能**：
- **单个Agent热更新**：`reload_agent(agent_key)` 方法
- **所有Agent热更新**：`reload_all_agents()` 方法
- **配置重新加载**：热更新时会重新加载配置文件
- **缓存自动更新**：热更新后，缓存会自动更新

**实现位置**：`domain/agents/factory.py`

#### 3.2.2 使用方法

**重新加载单个Agent**：
```python
from domain.agents.factory import AgentFactory

# 重新加载指定Agent
agent = AgentFactory.reload_agent("blood_pressure_agent")
```

**重新加载所有Agent**：
```python
# 重新加载所有Agent
agents = AgentFactory.reload_all_agents()
print(f"重新加载了 {len(agents)} 个Agent")
```

**注意事项**：
- 热更新后，**需要重新构建路由图**才能生效（因为路由图在创建时已经引用了旧的Agent实例）
- 建议在路由图创建时使用 `AgentFactory.create_agent()` 获取Agent，这样热更新后重新创建路由图即可

#### 3.2.3 API端点

提供了RESTful API端点，支持通过HTTP请求触发热更新：

**重新加载指定Agent**：
```http
POST /api/v1/agents/{agent_key}/reload
```

**示例**：
```bash
curl -X POST http://localhost:8000/api/v1/agents/blood_pressure_agent/reload
```

**响应**：
```json
{
  "message": "Agent重新加载成功",
  "agent_key": "blood_pressure_agent",
  "cached": true
}
```

**重新加载所有Agent**：
```http
POST /api/v1/agents/reload-all
```

**示例**：
```bash
curl -X POST http://localhost:8000/api/v1/agents/reload-all
```

**响应**：
```json
{
  "message": "所有Agent重新加载成功",
  "agent_count": 5,
  "agent_keys": ["blood_pressure_agent", "appointment_agent", ...]
}
```

**获取缓存统计**：
```http
GET /api/v1/agents/cache/stats
```

**示例**：
```bash
curl http://localhost:8000/api/v1/agents/cache/stats
```

**响应**：
```json
{
  "cache_stats": {
    "hits": 10,
    "misses": 5,
    "created": 5,
    "reloaded": 2,
    "cleared": 1,
    "cache_size": 5,
    "cached_agents": ["blood_pressure_agent", "appointment_agent", ...],
    "hit_rate": 0.6666666666666666
  }
}
```

**清除缓存**：
```http
DELETE /api/v1/agents/cache?agent_key={agent_key}
```

**示例**：
```bash
# 清除单个Agent缓存
curl -X DELETE "http://localhost:8000/api/v1/agents/cache?agent_key=blood_pressure_agent"

# 清除所有缓存
curl -X DELETE http://localhost:8000/api/v1/agents/cache
```

---

## 阶段四：测试与文档

### 4.1 单元测试

#### 4.1.1 测试覆盖

完成了以下组件的单元测试：

1. **LangfusePromptAdapter测试**（`test_langfuse_adapter.py`）
   - 从Langfuse获取模版
   - 模版缓存机制
   - Langfuse不可用时的降级
   - 清除缓存
   - 检查Langfuse是否可用

2. **LangfuseLoader测试**（`test_langfuse_loader.py`）
   - 从Langfuse加载模版
   - 加载指定版本的模版
   - 占位符填充
   - 支持langfuse://协议
   - 适配器延迟初始化

3. **PlaceholderManager测试**（`test_placeholder_manager.py`）
   - 系统占位符提取
   - Agent特定占位符
   - 占位符填充
   - 清除Agent占位符

4. **AgentRegistry测试**（`test_agent_registry.py`）
   - Agent注册
   - 从配置文件加载
   - 获取节点名称和意图类型
   - 检查Agent是否已注册
   - 清除注册

5. **AgentFactory缓存测试**（`test_agent_factory_cache.py`）
   - Agent缓存机制
   - 强制重新加载
   - 配置更新检测
   - 重新加载Agent
   - 清除缓存
   - 缓存统计

**测试文件位置**：`cursor_test/M3_test/langfuse/`

#### 4.1.2 运行测试

**运行所有单元测试**：
```bash
# 在项目根目录运行
pytest cursor_test/M3_test/langfuse/ -v
```

**运行特定测试文件**：
```bash
pytest cursor_test/M3_test/langfuse/test_agent_factory_cache.py -v
```

**运行特定测试用例**：
```bash
pytest cursor_test/M3_test/langfuse/test_agent_factory_cache.py::test_agent_caching -v
```

### 4.2 集成测试

#### 4.2.1 测试覆盖

完成了以下集成测试：

1. **Agent缓存机制集成测试**（`test_agent_cache_integration.py`）
   - 路由图创建时Agent缓存的使用
   - 配置更新后缓存清除
   - 在路由图创建后重新加载Agent
   - Agent缓存的性能提升
   - 多个Agent的缓存

2. **Langfuse提示词加载集成测试**（`test_langfuse_prompt_integration.py`）
   - 使用Langfuse提示词创建Agent
   - Langfuse不可用时的降级
   - Langfuse提示词缓存

**测试文件位置**：`cursor_test/M3_test/langfuse/`

#### 4.2.2 运行测试

**运行所有集成测试**：
```bash
pytest cursor_test/M3_test/langfuse/test_*_integration.py -v
```

### 4.3 文档更新

#### 4.3.1 新增文档

- **本文档**：阶段三和阶段四开发总结
- **API文档**：热更新API端点说明（已添加到 `app/api/routes.py`）

#### 4.3.2 文档位置

- 开发总结：`cursor_docs/阶段三Agent生命周期管理与阶段四测试文档开发总结.md`
- API文档：通过Swagger UI访问（`http://localhost:8000/docs`）

---

## 开发指南

### 如何添加新Agent

#### 步骤1：创建工具（如果需要）

如果新Agent需要新的工具，首先在 `domain/tools/` 下创建工具：

```python
# domain/tools/new_feature/record_new_feature.py
from langchain_core.tools import tool
from domain.router.state import RouterState

@tool
def record_new_feature(feature_data: str) -> str:
    """记录新功能数据"""
    # 实现工具逻辑
    return f"已记录: {feature_data}"
```

然后在 `domain/tools/registry.py` 中注册：

```python
from domain.tools.new_feature.record_new_feature import record_new_feature

TOOL_REGISTRY = {
    # ... 其他工具
    "record_new_feature": record_new_feature,
}
```

#### 步骤2：配置Agent

在 `config/agents.yaml` 中添加新Agent配置：

```yaml
agents:
  new_feature_agent:
    name: "新功能智能体"
    description: "负责处理新功能相关的请求"
    llm:
      temperature: 0.7
    tools:
      - record_new_feature
      - query_new_feature
    
    # 提示词配置（优先使用Langfuse）
    langfuse_template: "new_feature_agent_prompt"
    
    # 占位符配置（Agent特定，可选）
    placeholders:
      feature_type: "新功能类型"
    
    # 路由配置（必需）
    routing:
      node_name: "new_feature_agent"
      intent_type: "new_feature"
    
    # 降级配置（可选）
    system_prompt_path: "config/prompts/new_feature_prompt.txt"
```

#### 步骤3：在Langfuse中创建提示词模版（如果使用Langfuse）

1. 登录Langfuse Dashboard
2. 进入 "Prompts" 页面
3. 点击 "Create Prompt"
4. 输入模版名称：`new_feature_agent_prompt`
5. 粘贴提示词内容（支持占位符，如 `{{user_id}}`、`{{session_id}}`）
6. 保存模版

#### 步骤4：验证

**验证Agent配置**：
```python
from domain.agents.factory import AgentFactory

# 列出所有Agent
agents = AgentFactory.list_agents()
assert "new_feature_agent" in agents

# 创建Agent（测试）
agent = AgentFactory.create_agent("new_feature_agent")
```

**验证路由图**：
路由图会自动从 `AgentRegistry` 加载所有Agent，无需手动修改代码。

#### 注意事项

1. **路由配置必需**：每个Agent必须配置 `routing.node_name` 和 `routing.intent_type`
2. **意图类型唯一**：`intent_type` 应该与路由工具中定义的意图类型一致
3. **工具注册**：确保所有工具都在 `TOOL_REGISTRY` 中注册
4. **提示词模版**：如果使用Langfuse，确保模版名称与配置中的 `langfuse_template` 一致

---

## 配置说明

### agents.yaml 配置格式

#### 完整配置示例

```yaml
agents:
  # Agent键名（用于代码中引用）
  blood_pressure_agent:
    # 基本信息
    name: "血压记录智能体"
    description: "负责处理用户血压相关的请求"
    
    # LLM配置
    llm:
      model: "deepseek-chat"  # 可选，不指定则使用环境变量中的 LLM_MODEL
      temperature: 0.7         # 可选，默认使用环境变量中的 LLM_TEMPERATURE_DEFAULT
    
    # 工具列表（从 TOOL_REGISTRY 获取）
    tools:
      - record_blood_pressure
      - query_blood_pressure
      - update_blood_pressure
    
    # 提示词配置（优先级：Langfuse > PromptManager > system_prompt > system_prompt_path）
    langfuse_template: "blood_pressure_agent_prompt"  # Langfuse模版名称
    langfuse_template_version: "v1.0"                # 可选：指定模版版本
    
    # 占位符配置（Agent特定，可选）
    placeholders:
      normal_range: "收缩压 90-140 mmHg，舒张压 60-90 mmHg"
      measurement_time_format: "YYYY-MM-DD HH:mm"
    
    # 路由配置（必需）
    routing:
      node_name: "blood_pressure_agent"  # 路由图中的节点名称
      intent_type: "blood_pressure"       # 对应的意图类型
    
    # 降级配置（可选，Langfuse不可用时使用）
    system_prompt: "你是一个血压记录助手"  # 直接配置提示词
    system_prompt_path: "config/prompts/blood_pressure_prompt.txt"  # 从文件加载提示词
```

#### 配置项说明

| 配置项 | 类型 | 必需 | 说明 |
|--------|------|------|------|
| `name` | string | 是 | Agent名称 |
| `description` | string | 否 | Agent描述 |
| `llm.model` | string | 否 | LLM模型名称 |
| `llm.temperature` | float | 否 | LLM温度参数 |
| `tools` | list | 是 | 工具列表（工具名称） |
| `langfuse_template` | string | 否 | Langfuse模版名称 |
| `langfuse_template_version` | string | 否 | Langfuse模版版本 |
| `placeholders` | dict | 否 | Agent特定占位符 |
| `routing.node_name` | string | 是 | 路由图中的节点名称 |
| `routing.intent_type` | string | 是 | 对应的意图类型 |
| `system_prompt` | string | 否 | 系统提示词（降级用） |
| `system_prompt_path` | string | 否 | 提示词文件路径（降级用） |

#### 提示词加载优先级

1. **Langfuse模版**（如果配置了 `langfuse_template` 且启用了Langfuse）
2. **PromptManager**（如果配置了提示词模板系统）
3. **system_prompt**（配置文件中的直接提示词）
4. **system_prompt_path**（从文件加载提示词）

---

## API接口说明

### Agent管理接口

#### 1. 重新加载指定Agent

**接口**：`POST /api/v1/agents/{agent_key}/reload`

**路径参数**：
- `agent_key`：Agent键名（如 `blood_pressure_agent`）

**响应**：
```json
{
  "message": "Agent重新加载成功",
  "agent_key": "blood_pressure_agent",
  "cached": true
}
```

#### 2. 重新加载所有Agent

**接口**：`POST /api/v1/agents/reload-all`

**响应**：
```json
{
  "message": "所有Agent重新加载成功",
  "agent_count": 5,
  "agent_keys": ["blood_pressure_agent", "appointment_agent", ...]
}
```

#### 3. 获取缓存统计

**接口**：`GET /api/v1/agents/cache/stats`

**响应**：
```json
{
  "cache_stats": {
    "hits": 10,
    "misses": 5,
    "created": 5,
    "reloaded": 2,
    "cleared": 1,
    "cache_size": 5,
    "cached_agents": ["blood_pressure_agent", "appointment_agent", ...],
    "hit_rate": 0.6666666666666666
  }
}
```

#### 4. 清除缓存

**接口**：`DELETE /api/v1/agents/cache`

**查询参数**：
- `agent_key`（可选）：Agent键名，如果不提供则清除所有缓存

**响应**：
```json
{
  "message": "Agent缓存已清除: blood_pressure_agent",
  "agent_key": "blood_pressure_agent"
}
```

---

## 总结

### 完成内容

✅ **阶段三：Agent生命周期管理**
- [x] 实现Agent缓存机制
- [x] 实现配置更新检测
- [x] 实现缓存清理机制
- [x] 添加缓存统计和监控
- [x] 实现 `reload_agent()` 方法
- [x] 实现配置热更新检测
- [x] 添加热更新API端点

✅ **阶段四：测试与文档**
- [x] LangfusePromptAdapter单元测试
- [x] LangfuseLoader单元测试
- [x] PlaceholderManager单元测试
- [x] AgentRegistry单元测试
- [x] AgentFactory增强功能测试
- [x] Langfuse提示词加载集成测试
- [x] 动态路由图构建集成测试
- [x] Agent缓存机制集成测试
- [x] 完整流程端到端测试
- [x] 更新开发指南
- [x] 更新配置说明
- [x] 更新API文档

### 技术亮点

1. **线程安全的缓存机制**：使用线程锁保证多线程环境下的安全性
2. **自动配置更新检测**：无需手动操作，配置更新后自动清除缓存
3. **完整的统计监控**：提供缓存命中率、缓存大小等统计信息
4. **RESTful API支持**：支持通过HTTP请求触发热更新
5. **完善的测试覆盖**：单元测试和集成测试覆盖所有核心功能

### 性能提升

- **缓存命中率**：通过Agent缓存，避免重复创建Agent实例，显著提升性能
- **配置更新检测**：自动检测配置更新，无需重启应用
- **热更新支持**：支持在不重启应用的情况下更新Agent配置

### 后续优化方向

1. **文件监控**：实现配置文件监控（如使用 `watchdog`），自动检测配置更新
2. **缓存策略优化**：支持LRU等缓存淘汰策略
3. **性能监控**：添加Agent创建时间、缓存命中率等性能指标
4. **分布式缓存**：支持Redis等分布式缓存（如果需要）

---

## 参考文档

- [V4.1 Agent优化+Langfuse接入开发方案](./doc/设计V4.0/V4.1%20Agent优化+Langfuse接入/开发方案与实施计划.md)
- [Langfuse提示词模版对接使用指南](./cursor_docs/Langfuse提示词模版对接使用指南.md)
- [阶段一Langfuse提示词模版对接开发总结](./cursor_docs/阶段一Langfuse提示词模版对接开发总结.md)

