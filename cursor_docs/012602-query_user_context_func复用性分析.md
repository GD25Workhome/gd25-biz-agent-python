# query_user_context_func 复用性分析文档

## 一、需求概述

### 1.1 需求背景

在 `medical_agent_v6_1` 流程中，需要开发一个流程启动时的基础数据查询节点 `builder_prompt_context_node`，该节点需要：

1. **功能目标**：查询用户的血压数据，并将数据存储到 `state.prompt_vars` 中
2. **节点配置**：使用 `function_key: "query_user_context_func"`
3. **数据存储位置**：`state.prompt_vars`（下级节点自行取值，决定如何设置上下文）

### 1.2 现有实现

项目中已存在一个类似的节点实现：

- **节点类**：`QueryUserInfoNode`
- **function_key**：`query_user_info_node_func`
- **文件位置**：`backend/domain/flows/implementations/query_user_info_node.py`
- **功能**：查询用户的血压数据，存储到 `state.prompt_vars["blood_pressure_list"]`

## 二、功能对比分析

### 2.1 功能需求对比

| 对比项 | query_user_info_node_func | query_user_context_func（需求） |
|--------|---------------------------|--------------------------------|
| **查询数据类型** | 血压数据（BloodPressureRecord） | 血压数据（用户提到 embedding_record，但实际应为血压数据） |
| **数据来源** | `BloodPressureRecord` 表 | 血压数据（需确认是否从 embedding_record） |
| **存储位置** | `state.prompt_vars["blood_pressure_list"]` | `state.prompt_vars`（未指定具体字段名） |
| **查询逻辑** | 调用 `query_blood_pressure_raw()` | 相同（查询血压数据） |
| **时间范围** | 默认14天 | 未指定（可能相同） |
| **配置驱动** | 支持 `query_list` 配置 | 未指定（可能不需要） |

### 2.2 代码实现对比

#### 2.2.1 现有实现（query_user_info_node_func）

```python
class QueryUserInfoNode(BaseFunctionNode):
    @classmethod
    def get_key(cls) -> str:
        return "query_user_info_node_func"
    
    async def execute(self, state: FlowState) -> FlowState:
        # 1. 检查配置中是否包含 blood_pressure
        if not self._has_blood_pressure_in_config():
            return state
        
        # 2. 查询血压数据
        blood_pressure_data = await self._query_blood_pressure()
        
        # 3. 存储到 state.prompt_vars["blood_pressure_list"]
        new_state["prompt_vars"]["blood_pressure_list"] = blood_pressure_data
        
        return new_state
```

#### 2.2.2 需求实现（query_user_context_func）

根据需求描述，新节点应该：
- 查询血压数据
- 存储到 `state.prompt_vars`（未指定具体字段名）
- 功能与现有实现高度相似

## 三、复用性分析

### 3.1 功能相似度：95%

**相似点**：
1. ✅ 都查询血压数据
2. ✅ 都使用 `query_blood_pressure_raw()` 工具函数
3. ✅ 都存储到 `state.prompt_vars`
4. ✅ 都处理用户ID获取（通过工具内部处理）
5. ✅ 都处理时间范围（默认14天）

**差异点**：
1. ⚠️ **function_key 不同**：`query_user_info_node_func` vs `query_user_context_func`
2. ⚠️ **存储字段名可能不同**：`blood_pressure_list` vs 未指定（可能相同）
3. ⚠️ **配置检查逻辑**：现有实现有 `_has_blood_pressure_in_config()` 检查，新需求可能不需要

### 3.2 复用方案评估

#### 方案A：直接复用（推荐度：⭐⭐⭐⭐⭐）

**方案描述**：直接使用 `query_user_info_node_func`，在 flow.yaml 中配置 `function_key: "query_user_info_node_func"`

**优点**：
- ✅ 无需开发新代码
- ✅ 功能完全匹配
- ✅ 维护成本低
- ✅ 代码复用率高

**缺点**：
- ⚠️ function_key 名称不匹配（但功能相同，可以接受）
- ⚠️ 如果后续两个节点需要不同行为，需要修改

**适用场景**：
- 两个节点的功能完全一致
- 可以接受使用相同的 function_key

**实现方式**：
```yaml
# config/flows/medical_agent_v6_1/flow.yaml
nodes:
  - name: builder_prompt_context_node
    type: function
    config:
      function_key: "query_user_info_node_func"  # 直接复用
      query_list:
        - blood_pressure
```

#### 方案B：创建新节点类（推荐度：⭐⭐⭐）

**方案描述**：创建新的 `QueryUserContextNode` 类，但内部实现复用 `QueryUserInfoNode` 的逻辑

**优点**：
- ✅ function_key 名称匹配需求
- ✅ 语义更清晰（context vs info）
- ✅ 后续可以独立扩展

**缺点**：
- ❌ 代码重复
- ❌ 维护成本增加
- ❌ 功能完全一致，没有必要

**适用场景**：
- 两个节点后续可能有不同的扩展需求
- 需要保持语义清晰

**实现方式**：
```python
class QueryUserContextNode(BaseFunctionNode):
    @classmethod
    def get_key(cls) -> str:
        return "query_user_context_func"
    
    async def execute(self, state: FlowState) -> FlowState:
        # 直接调用 QueryUserInfoNode 的逻辑
        query_node = QueryUserInfoNode()
        return await query_node.execute(state)
```

#### 方案C：修改现有节点支持别名（推荐度：⭐⭐⭐⭐）

**方案描述**：修改 `QueryUserInfoNode` 支持多个 function_key，或创建别名注册

**优点**：
- ✅ 代码不重复
- ✅ 支持多个 function_key
- ✅ 语义清晰

**缺点**：
- ⚠️ 需要修改注册机制
- ⚠️ 实现复杂度稍高

**适用场景**：
- 需要支持多个 function_key 指向同一个实现
- 需要保持代码简洁

**实现方式**：
```python
class QueryUserInfoNode(BaseFunctionNode):
    @classmethod
    def get_key(cls) -> str:
        return "query_user_info_node_func"
    
    @classmethod
    def get_aliases(cls) -> List[str]:
        """返回别名列表"""
        return ["query_user_context_func"]
```

## 四、数据模型确认

### 4.1 用户提到的数据源

用户提到：**"我需要将用户的血压数据 @backend/infrastructure/database/models/embedding_record.py 数据查询出来"**

### 4.2 实际数据源分析

**embedding_record.py 分析**：
- `EmbeddingRecord` 模型用于存储词干提取后的结构化数据
- 包含字段：`scene_summary`、`optimization_question`、`input_tags`、`response_tags`、`ai_response` 等
- **不包含血压数据字段**（如 systolic、diastolic、heart_rate）

**血压数据实际来源**：
- 数据模型：`BloodPressureRecord`（在 `backend/infrastructure/database/models/blood_pressure.py`）
- 查询工具：`query_blood_pressure_raw()`（在 `backend/domain/tools/blood_pressure_tool.py`）
- 现有实现：`QueryUserInfoNode` 已正确使用 `BloodPressureRecord`

### 4.3 结论

**用户可能混淆了数据源**：
- ❌ `EmbeddingRecord` 不包含血压数据
- ✅ 血压数据应该从 `BloodPressureRecord` 查询
- ✅ 现有实现 `query_user_info_node_func` 已正确实现血压数据查询

## 五、推荐方案

### 5.1 推荐方案：方案A（直接复用）

**理由**：
1. **功能完全匹配**：两个节点的功能需求完全一致
2. **代码质量**：现有实现已经完善，包括错误处理、日志记录等
3. **维护成本**：复用现有代码，无需维护两套逻辑
4. **语义可接受**：虽然 function_key 名称不同，但功能相同，可以接受

### 5.2 实施步骤

1. **在 flow.yaml 中配置**：
   ```yaml
   nodes:
     - name: builder_prompt_context_node
       type: function
       config:
         function_key: "query_user_info_node_func"  # 复用现有实现
         query_list:
           - blood_pressure
   ```

2. **验证功能**：
   - 确认节点能正确查询血压数据
   - 确认数据存储到 `state.prompt_vars["blood_pressure_list"]`
   - 确认下级节点能正确读取数据

3. **文档更新**：
   - 在 flow.yaml 中添加注释说明复用关系
   - 更新相关文档说明节点复用情况

### 5.3 如果必须使用新 function_key

如果业务上必须使用 `query_user_context_func` 作为 function_key，推荐使用**方案C（别名支持）**：

**实施步骤**：
1. 修改 `QueryUserInfoNode` 支持别名注册
2. 在注册表中注册别名 `query_user_context_func` -> `QueryUserInfoNode`
3. 在 flow.yaml 中使用 `function_key: "query_user_context_func"`

**代码修改示例**：
```python
# backend/domain/flows/nodes/function_registry.py
# 在注册时支持别名
function_registry.register_alias("query_user_context_func", QueryUserInfoNode)
```

## 六、注意事项

### 6.1 数据存储字段名

**当前实现**：数据存储到 `state.prompt_vars["blood_pressure_list"]`

**需求说明**：需求中提到"output 的逻辑采用规范【state.prompt_vars】值进行存储，下级节点自行取值"

**建议**：
- 如果下级节点期望的字段名不同，可以在复用后添加数据转换逻辑
- 或者修改现有实现支持配置化的字段名

### 6.2 配置检查逻辑

**当前实现**：有 `_has_blood_pressure_in_config()` 检查，需要配置中包含 `blood_pressure`

**需求说明**：新节点可能不需要配置检查，直接查询血压数据

**建议**：
- 如果不需要配置检查，可以在 flow.yaml 中不配置 `query_list`，或修改现有实现支持"无配置时默认查询血压"

### 6.3 错误处理

**当前实现**：完善的错误处理，包括：
- 用户ID缺失处理
- 查询失败降级处理
- 异常捕获和日志记录

**建议**：复用现有实现的错误处理逻辑，无需修改

## 七、总结

### 7.1 复用性结论

**✅ 高度可复用**：`query_user_info_node_func` 的实现可以完全满足 `query_user_context_func` 的需求。

### 7.2 推荐方案

**推荐使用方案A（直接复用）**：
- 在 flow.yaml 中配置 `function_key: "query_user_info_node_func"`
- 无需开发新代码
- 功能完全匹配，维护成本低

### 7.3 如果必须使用新 function_key

**推荐使用方案C（别名支持）**：
- 修改注册机制支持别名
- 保持代码不重复
- 语义清晰

### 7.4 数据源确认

**重要**：血压数据应该从 `BloodPressureRecord` 查询，而不是从 `EmbeddingRecord`。现有实现已正确实现。

---

**文档生成时间**：2025-01-26  
**分析版本**：V1.0  
**相关代码路径**：
- `backend/domain/flows/implementations/query_user_info_node.py`
- `backend/domain/tools/blood_pressure_tool.py`
- `config/flows/medical_agent_v6_1/flow.yaml`
