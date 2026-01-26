# RAG Agent 节点设计文档

## 文档信息

- **创建日期**：2026-01-26
- **版本**：V1.0
- **状态**：设计阶段

---

## 一、需求概述

### 1.1 业务背景

在医疗 Agent 流程（`medical_agent_v6_1`）中，需要在优化节点（`optimization_agent`）和核心 Agent 节点（`core_agent`）之间插入一个 RAG 检索节点（`rag_agent`），用于：

1. 从前置节点获取优化后的查询文本
2. 通过向量检索从案例库中召回相似案例
3. 将检索结果作为 fewshot 示例传递给下游节点

### 1.2 流程位置

```
optimization_agent (opt_agent)
    ↓
    [输出: scene_summary, optimization_question]
    ↓
rag_agent (rag_agent) ← 当前开发节点
    ↓
    [输出: retrieved_examples]
    ↓
core_agent (agent)
```

---

## 二、前置节点输出分析

### 2.1 optimization_agent 输出格式

前置节点 `optimization_agent` 的输出为 JSON 格式，包含以下字段：

```json
{
  "scene_summary": "高血压患者今日记录血压182/112mmHg，属重度偏高，伴头晕，需紧急预警。",
  "optimization_question": "我刚测血压180/110，还有点头晕，这种情况危险吗？",
  "input_tags": ["高血压", "重度偏高", "头晕", "需预警", "record"],
  "response_tags": ["警示型", "预警提醒", "就医建议"]
}
```

### 2.2 数据传递方式

根据现有代码模式（参考 `agent_creator.py`），前置节点的输出会被自动提取并存储到 `FlowState.edges_var` 中：

- `edges_var["scene_summary"]`：场景摘要
- `edges_var["optimization_question"]`：优化后的问题

---

## 三、RAG Agent 节点设计

### 3.1 节点类型定义

- **节点类型**：`rag_agent`
- **节点名称**：`rag_node`（在 flow.yaml 中定义）
- **节点创建器**：`RagAgentNodeCreator`（新建）

### 3.2 配置结构

在 `flow.yaml` 中的配置示例：

```yaml
- name: rag_node
  type: rag_agent
  config:
    model:
      provider: doubao-embedding
      name: doubao-embedding-vision-250615
    # 可选配置
    query_field: "optimization_question"  # 用于检索的字段，默认使用 optimization_question
    top_k: 5  # 召回数量，默认 5
    similarity_threshold: 0.7  # 相似度阈值，默认 0.7
    output_field: "retrieved_examples"  # 输出字段名，默认 retrieved_examples
```

### 3.3 核心功能流程

```
1. 从前置节点获取数据
   ├─ 从 state.edges_var 读取 scene_summary 和 optimization_question
   └─ 验证数据完整性

2. 构建查询文本
   ├─ 优先使用 optimization_question（或配置的 query_field）
   └─ 可选：结合 scene_summary 增强查询

3. 生成 Embedding 向量
   ├─ 调用 embedding 模型（配置中的 model）
   └─ 将查询文本转换为向量

4. 向量库检索
   ├─ 在 embedding_record 表中检索相似案例
   ├─ 使用 pgvector 的余弦相似度计算
   └─ 支持降级策略（多个阈值）

5. 格式化检索结果
   ├─ 提取关键字段：scene_summary, optimization_question, ai_response
   └─ 格式化为 fewshot 示例文本

6. 输出到下游节点
   └─ 将结果存储到 state.edges_var[output_field] 或 state.prompt_vars
```

---

## 四、技术实现方案

### 4.1 向量检索方案

参考现有实现：`backend/infrastructure/rag/retrieval.py`

**核心检索逻辑**：

1. **单表检索**：在 `embedding_record` 表中执行向量相似度查询
2. **相似度计算**：使用 pgvector 的 `<=>` 操作符（余弦距离）
3. **降级策略**：如果结果不足，逐步降低阈值（0.7 → 0.6 → 0.5）
4. **结果排序**：按相似度降序排列

**SQL 查询示例**：

```sql
SELECT 
    id,
    scene_summary,
    optimization_question,
    ai_response,
    1 - (embedding_value <=> %s::vector) AS similarity_score
FROM gd2502_embedding_records
WHERE embedding_value IS NOT NULL
  AND 1 - (embedding_value <=> %s::vector) >= %s
  AND is_published = true  -- 只检索已发布的案例
ORDER BY embedding_value <=> %s::vector
LIMIT %s
```

### 4.2 Embedding 模型调用

参考现有实现：`backend/domain/embeddings/factory.py`

- 使用 `EmbeddingFactory.create_embedding_executor()` 创建执行器
- 支持异步调用：`await embedding_executor.ainvoke(texts)`

### 4.3 数据模型

**输入数据**（从前置节点）：
- `scene_summary`: str
- `optimization_question`: str

**检索结果**（从数据库）：
- `scene_summary`: str
- `optimization_question`: str
- `ai_response`: str
- `similarity`: float

**输出数据**（传递给下游节点）：
- `retrieved_examples`: str（格式化的 fewshot 文本）

---

## 五、节点创建器实现

### 5.1 类结构

```python
class RagAgentNodeCreator(NodeCreator):
    """RAG Agent 节点创建器"""
    
    def create(self, node_def: NodeDefinition, flow_def: FlowDefinition) -> Callable:
        """
        创建 RAG Agent 节点函数
        
        Returns:
            Callable: 节点函数（异步函数，接收 FlowState，返回 FlowState）
        """
        # 1. 解析配置
        # 2. 创建 embedding 执行器
        # 3. 创建节点函数
        # 4. 返回节点函数
```

### 5.2 节点函数逻辑

```python
async def rag_node_action(state: FlowState) -> FlowState:
    """RAG Agent 节点函数"""
    # 1. 从 edges_var 读取输入数据
    # 2. 调用 embedding 模型生成向量
    # 3. 执行向量检索
    # 4. 格式化检索结果
    # 5. 更新 state 并返回
```

### 5.3 错误处理

- **输入数据缺失**：抛出 `ValueError`，中断流程执行
- **Embedding 调用失败**：抛出 `RuntimeError`，中断流程执行
- **检索结果为空**：记录警告日志，返回空结果（不中断流程）

---

## 六、输出格式设计

### 6.1 Fewshot 示例格式

检索结果需要格式化为文本，供下游节点使用。建议格式：

```
## 相似案例示例

### 案例 1（相似度：0.85）
**用户场景**：高血压患者今日记录血压182/112mmHg，属重度偏高，伴头晕，需紧急预警。
**用户问题**：我刚测血压180/110，还有点头晕，这种情况危险吗？
**AI回复**：您本次测量的血压过高，且伴有不适症状，建议您尽快到医院就诊...

### 案例 2（相似度：0.82）
**用户场景**：...
**用户问题**：...
**AI回复**：...
```

### 6.2 存储位置

- **方案一**：存储到 `state.edges_var["retrieved_examples"]`
- **方案二**：存储到 `state.prompt_vars["retrieved_examples"]`

**推荐方案一**：与现有节点模式保持一致（参考 `agent_creator.py`）

---

## 七、节点注册

### 7.1 注册位置

在 `backend/domain/flows/nodes/registry.py` 的 `_init_default_creators()` 函数中添加：

```python
from backend.domain.flows.nodes.rag_agent_creator import RagAgentNodeCreator

node_creator_registry.register("rag_agent", RagAgentNodeCreator())
```

### 7.2 导出

在 `backend/domain/flows/nodes/__init__.py` 中添加导出：

```python
from backend.domain.flows.nodes.rag_agent_creator import RagAgentNodeCreator
```

---

## 八、依赖关系

### 8.1 数据库依赖

- **表**：`gd2502_embedding_records`（`EmbeddingRecord` 模型）
- **扩展**：PostgreSQL + pgvector 扩展
- **字段**：`embedding_value`（Vector(2048)）

### 8.2 基础设施依赖

- `backend.infrastructure.rag.retrieval`：向量检索功能（可复用或参考）
- `backend.domain.embeddings.factory`：Embedding 模型工厂
- `backend.infrastructure.database.vector_connection`：向量数据库连接

---

## 九、实现步骤（第一版本）

### 9.1 第一阶段：核心功能实现

1. ✅ **创建节点创建器类**
   - 文件：`backend/domain/flows/nodes/rag_agent_creator.py`
   - 实现配置解析和节点函数创建

2. ✅ **实现向量检索逻辑**
   - 复用或参考 `retrieval.py` 中的检索逻辑
   - 适配 `embedding_record` 表结构

3. ✅ **实现 Embedding 调用**
   - 使用 `EmbeddingFactory` 创建执行器
   - 异步调用生成向量

4. ✅ **实现结果格式化**
   - 将检索结果格式化为 fewshot 文本
   - 存储到 `state.edges_var`

5. ✅ **注册节点类型**
   - 在 `registry.py` 中注册 `rag_agent` 类型

### 9.2 第一版本简化项

- **暂不支持**：多字段组合查询（只使用单一字段）
- **暂不支持**：复杂的检索策略（使用基础降级策略）
- **暂不支持**：结果过滤和重排序（使用简单 Top-K）
- **暂不支持**：缓存机制（每次实时检索）

---

## 十、测试要点

### 10.1 功能测试

1. **正常流程测试**
   - 前置节点输出完整数据
   - 向量库中存在相似案例
   - 验证检索结果格式正确

2. **边界情况测试**
   - 前置节点输出缺失字段
   - 向量库中无相似案例
   - Embedding 调用失败

3. **性能测试**
   - 检索响应时间
   - 并发场景下的表现

### 10.2 集成测试

- 完整流程测试：`optimization_agent` → `rag_agent` → `core_agent`
- 验证下游节点能正确读取检索结果

---

## 十一、后续优化方向

1. **检索策略优化**
   - 支持多字段组合查询（scene_summary + optimization_question）
   - 支持标签过滤（基于 input_tags）
   - 支持重排序（基于质量评分）

2. **性能优化**
   - 添加缓存机制（查询文本 → 检索结果）
   - 批量检索优化

3. **功能扩展**
   - 支持多表检索（如需要）
   - 支持动态 Top-K 配置
   - 支持检索结果去重

---

## 十二、参考文档

- `backend/infrastructure/rag/retrieval.py`：向量检索实现参考
- `backend/domain/flows/nodes/embedding_creator.py`：Embedding 节点实现参考
- `backend/domain/flows/nodes/agent_creator.py`：Agent 节点实现参考
- `backend/infrastructure/database/models/embedding_record.py`：数据模型定义

---

**文档状态**：设计完成，待实现
