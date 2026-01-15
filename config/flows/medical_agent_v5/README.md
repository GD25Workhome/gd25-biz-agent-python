# Medical Agent V5 - 独立提示词聚合方案

## 方案概述

Medical Agent V5 是基于**提示词聚合 + RAG增强**设计的新流程版本，将原有的多Agent分离设计重构为3节点流程：

```
节点1：快速意图识别
    ↓
节点2：向量库检索 + 用户信息查询
    ↓
节点3：核心Agent（聚合所有功能）
```

## 核心优势

1. **提示词精简**：节点3只保留核心流程逻辑，问答示例通过RAG动态获取
2. **知识库可扩展**：优秀的历史问答和科普资料可随时更新到向量库
3. **个性化增强**：结合用户基础信息，提供更精准的回答
4. **流程简化**：从多Agent分离改为三节点流程，更易维护

## 文件结构

```
medical_agent_v5/
├── flow.yaml                          # 流程配置文件
├── prompts/
│   ├── 01-intent_recognition.md      # 节点1：意图识别提示词
│   └── 03-core_agent.md              # 节点3：核心Agent提示词
└── README.md                          # 本文档
```

## 节点说明

### 节点1：意图识别（intent_recognition）

**职责**：
- 快速识别用户意图（record、query、qa、greeting）
- 提取核心信息（实体、问题类型）
- 生成优化的查询文本，用于向量库检索

**提示词**：`prompts/01-intent_recognition.md`

**输出**：
- `intent`: 意图类型
- `confidence`: 置信度
- `core_info`: 核心信息（entities, query_text, question_type）

### 节点2：检索节点（retrieval_node）

**职责**：
- 基于节点1的查询文本，从向量库检索相关示例
- 查询用户基础信息
- 整合检索结果和用户信息，传递给节点3

**类型**：函数节点（function node），非Agent

**实现位置**：需要在 GraphBuilder 中实现自定义函数节点

**输出**（更新到状态）：
- `retrieved_examples`: 检索到的示例列表
- `user_info`: 用户基础信息

### 节点3：核心Agent（core_agent）

**职责**：
- 整合所有功能：数据记录、数据查询、健康问答、日常问候
- 基于检索的示例和用户信息，生成个性化回答

**提示词**：`prompts/03-core_agent.md`

**占位符**：
- `{retrieved_examples}`: 检索示例（运行时动态注入）
- `{user_info}`: 用户信息（运行时动态注入）

**工具**：
- 记录工具：record_blood_pressure, record_medication, record_symptom, record_health_event
- 查询工具：query_blood_pressure, query_medication, query_symptom, query_health_event

## 状态字段

需要在 `RouterState` 中新增以下字段：

```python
class RouterState(TypedDict):
    # 原有字段
    messages: List[BaseMessage]
    current_intent: Optional[str]
    current_agent: Optional[str]
    
    # 新增字段（阶段二）
    core_info: Optional[Dict]  # 节点1提取的核心信息
    retrieved_examples: Optional[List[Dict]]  # 节点2检索的示例
    user_info: Optional[Dict]  # 节点2查询的用户信息
```

## 占位符替换机制

节点3的提示词包含以下占位符，需要在运行时动态替换：

1. **{retrieved_examples}**：格式化的检索示例文本
   - 格式：从 `retrieved_examples` 状态字段中提取并格式化

2. **{user_info}**：格式化的用户信息文本
   - 格式：从 `user_info` 状态字段中提取并格式化

3. **系统自动填充的占位符**：
   - `{llm_context_part}`：上下文信息
   - `{llm_rule_part}`：核心原则
   - `{end_llm_resopnse}`：输出格式要求

**实现位置**：在 GraphBuilder 中，创建节点3时动态构建提示词

## 流程验证

### 验证项

1. **流程结构验证**：
   - ✅ 节点配置正确：intent_recognition, retrieval_node, core_agent
   - ✅ 边配置正确：intent_recognition -> retrieval_node -> core_agent -> END
   - ✅ 入口节点：intent_recognition

2. **状态流转验证**：
   - ✅ 节点1输出 core_info 到状态
   - ✅ 节点2输出 retrieved_examples 和 user_info 到状态
   - ✅ 节点3读取状态并使用占位符替换

3. **占位符替换验证**：
   - ✅ {retrieved_examples} 正确替换
   - ✅ {user_info} 正确替换

## 下一步工作

阶段三：Python代码改造与功能测试

1. **向量库基础建设**
2. **数据导入功能**
3. **节点2实现（retrieval_node）**
4. **节点3提示词动态构建**
5. **错误处理与降级**
6. **功能测试**

## 参考文档

- 详细设计方案：`doc/V8.0独立提示词方案/独立提示词聚合方案设计.md`
- 原流程参考：`config/flows/medical_agent_v3/`

---

**文档版本**: v1.0  
**创建时间**: 2025-01-XX  
**对应流程版本**: medical_agent_v5
