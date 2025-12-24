# Langfuse提示词模版对接使用指南

## 概述

本文档说明如何使用Langfuse提示词模版功能，包括配置、使用方式和最佳实践。

## 功能特性

1. **从Langfuse获取提示词模版**：支持从Langfuse平台获取和管理提示词
2. **模版缓存机制**：自动缓存模版内容，减少API调用
3. **降级机制**：Langfuse不可用时自动降级到本地文件
4. **占位符支持**：支持系统占位符和Agent特定占位符
5. **版本管理**：支持指定模版版本

## 配置说明

### 1. 环境变量配置

在 `.env` 文件中添加以下配置：

```env
# Langfuse配置
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-xxx
LANGFUSE_SECRET_KEY=sk-xxx
LANGFUSE_HOST=https://cloud.langfuse.com  # 或自托管地址

# 提示词配置
PROMPT_USE_LANGFUSE=true  # 是否优先使用Langfuse（默认true）
PROMPT_CACHE_TTL=300      # 提示词缓存TTL（秒）
```

### 2. agents.yaml配置格式

在 `config/agents.yaml` 中配置Agent使用Langfuse模版：

```yaml
agents:
  blood_pressure_agent:
    name: "血压记录智能体"
    description: "帮助用户记录和管理血压数据"
    
    # LLM配置
    llm:
      model: "deepseek-chat"
      temperature: 0.7
    
    # 工具列表
    tools:
      - record_blood_pressure
      - query_blood_pressure
    
    # 提示词配置（优先使用Langfuse）
    langfuse_template: "blood_pressure_agent_prompt"  # Langfuse模版名称
    langfuse_template_version: "v1.0"  # 可选：指定模版版本
    
    # 占位符配置（Agent特定）
    placeholders:
      normal_range: "收缩压 90-140 mmHg，舒张压 60-90 mmHg"
      measurement_time_format: "YYYY-MM-DD HH:mm"
    
    # 或使用本地文件（fallback）
    # system_prompt_path: "config/prompts/modules/blood_pressure/role.txt"
```

## 使用方式

### 1. 在Langfuse中创建提示词模版

1. 登录Langfuse Dashboard
2. 进入 "Prompts" 页面
3. 创建新的提示词模版，名称如 `blood_pressure_agent_prompt`
4. 在模版内容中可以使用占位符，格式：`{{placeholder_name}}`

示例模版内容：

```
你是一个专业的血压记录助手。你的职责是帮助用户记录、查询和管理血压数据。

用户ID: {{user_id}}
会话ID: {{session_id}}
当前日期: {{current_date}}

正常血压范围: {{normal_range}}
测量时间格式: {{measurement_time_format}}

功能说明：
1. 记录血压：当用户提供血压数据时，使用 record_blood_pressure 工具记录
2. 查询血压：当用户询问血压记录时，使用 query_blood_pressure 工具查询
...
```

### 2. 系统占位符

系统占位符会自动从RouterState中提取：

- `{{user_id}}`: 用户ID
- `{{session_id}}`: 会话ID
- `{{current_date}}`: 当前日期（YYYY-MM-DD）
- `{{current_time}}`: 当前时间（HH:MM:SS）
- `{{current_datetime}}`: 当前日期时间（YYYY-MM-DD HH:MM:SS）

### 3. Agent特定占位符

在 `agents.yaml` 的 `placeholders` 配置中定义：

```yaml
placeholders:
  normal_range: "收缩压 90-140 mmHg，舒张压 60-90 mmHg"
  measurement_time_format: "YYYY-MM-DD HH:mm"
```

### 4. 代码使用

AgentFactory会自动从Langfuse加载提示词（如果配置了`langfuse_template`）：

```python
from domain.agents.factory import AgentFactory

# 创建Agent（会自动从Langfuse加载提示词）
agent = AgentFactory.create_agent("blood_pressure_agent")
```

## 降级机制

如果Langfuse服务不可用，系统会自动降级到本地文件：

1. 首先尝试从Langfuse获取模版
2. 如果失败，尝试从以下路径查找本地文件：
   - `config/prompts/{template_name}.txt`
   - `config/prompts/templates/{template_name}.txt`
   - `config/prompts/{template_name}.yaml`
3. 如果都失败，抛出异常

## 缓存机制

- 模版内容会自动缓存，默认TTL为300秒（可通过`PROMPT_CACHE_TTL`配置）
- 缓存键格式：`{template_name}:{version or 'latest'}`
- 可以通过`LangfusePromptAdapter.clear_cache()`手动清除缓存

## 测试

运行测试用例：

```bash
# 测试占位符管理器
pytest cursor_test/M3_test/langfuse/test_placeholder_manager.py -v

# 测试Langfuse适配器（需要配置Langfuse凭据）
pytest cursor_test/M3_test/langfuse/test_langfuse_adapter.py -v
```

## 注意事项

1. **Langfuse服务可用性**：确保Langfuse服务可访问，否则会降级到本地文件
2. **占位符命名**：占位符名称不能包含特殊字符，建议使用小写字母和下划线
3. **版本管理**：建议在Langfuse中为每个模版创建版本，便于回滚
4. **性能考虑**：模版缓存可以减少API调用，但需要注意缓存TTL设置

## 故障排查

### 问题1：无法从Langfuse获取模版

**可能原因**：
- Langfuse未启用或配置错误
- 模版名称不存在
- 网络连接问题

**解决方法**：
1. 检查环境变量配置
2. 确认模版名称正确
3. 检查Langfuse服务是否可访问
4. 查看日志中的错误信息

### 问题2：占位符未填充

**可能原因**：
- 占位符名称不匹配
- Agent特定占位符未配置

**解决方法**：
1. 检查占位符名称是否正确
2. 确认在`agents.yaml`中配置了`placeholders`
3. 查看日志中的警告信息

### 问题3：缓存未生效

**可能原因**：
- 缓存TTL设置过短
- 模版版本变化

**解决方法**：
1. 检查`PROMPT_CACHE_TTL`配置
2. 确认模版版本是否变化
3. 手动清除缓存后重试

## 后续优化

1. **A/B测试**：利用Langfuse的A/B测试功能
2. **性能监控**：基于Langfuse数据分析优化提示词
3. **成本分析**：基于Langfuse的成本分析优化模型使用

