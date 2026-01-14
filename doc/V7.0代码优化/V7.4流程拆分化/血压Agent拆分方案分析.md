# 血压Agent拆分方案分析

## 一、拆分目标

将当前的 `blood_pressure_agent` 拆分为两个独立的Agent节点：
1. **数据收集Agent** (`blood_pressure_collect_agent`)：负责收集血压数据（记录、查询、更新）
2. **数据点评Agent** (`blood_pressure_review_agent`)：负责血压健康点评

## 二、当前架构分析

### 2.1 当前实现方式

当前 `blood_pressure_agent` 是一个**单体Agent**，在一个Agent中同时完成：
- 数据收集（通过工具：`record_blood_pressure`、`query_blood_pressure`、`update_blood_pressure`）
- 数据点评（通过LLM根据历史数据生成点评）

**工作流程**：
```
用户输入 → blood_pressure_agent → 
  ├─ 收集数据（调用工具）→ 
  └─ 自动点评（LLM生成）→ 
  输出结果
```

### 2.2 代码框架特点

根据代码分析，当前框架具有以下特点：

1. **配置驱动**：流程通过YAML文件定义，包含nodes和edges
2. **节点独立性**：每个Agent节点有独立的prompt文件、model配置、tools配置
3. **流程构建**：`GraphBuilder` 从 `FlowDefinition` 构建LangGraph，无需修改Python代码
4. **Agent创建**：`AgentFactory` 根据配置创建Agent，支持动态加载prompt和tools

**关键代码路径**：
- 流程定义：`backend/domain/flows/definition.py`
- 流程解析：`backend/domain/flows/parser.py`
- 图构建：`backend/domain/flows/builder.py`
- Agent创建：`backend/domain/agents/factory.py`

## 三、拆分方案设计

### 3.1 拆分后的节点设计

#### 3.1.1 数据收集Agent (`blood_pressure_collect_agent`)

**职责**：
- 收集用户的血压数据（收缩压、舒张压、心率等）
- 支持多轮对话，主动询问缺失信息
- 调用工具：`record_blood_pressure`、`query_blood_pressure`、`update_blood_pressure`
- 数据收集完成后，**不进行点评**，只确认数据记录成功

**Prompt文件**：`prompts/11-blood_pressure_collect_agent.md`

**工具配置**：
```yaml
tools:
  - record_blood_pressure
  - query_blood_pressure
  - update_blood_pressure
```

#### 3.1.2 数据点评Agent (`blood_pressure_review_agent`)

**职责**：
- 接收已记录的血压数据（从state中获取）
- 查询历史血压数据（调用 `query_blood_pressure` 工具）
- 根据血压点评规则生成专业的健康点评
- **不进行数据收集**，只专注于点评

**Prompt文件**：`prompts/12-blood_pressure_review_agent.md`

**工具配置**：
```yaml
tools:
  - query_blood_pressure  # 用于获取历史数据
```

### 3.2 流程组合方案

#### 方案A：顺序执行（推荐）

**适用场景**：记录血压后自动点评

**流程图**：
```
intent_recognition 
  → blood_pressure_collect_agent (收集数据)
  → blood_pressure_review_agent (自动点评)
  → END
```

**YAML配置示例**：
```yaml
nodes:
  - name: blood_pressure_collect_agent
    type: agent
    config:
      prompt: prompts/11-blood_pressure_collect_agent.md
      model:
        provider: doubao
        name: doubao-seed-1-6-251015
        temperature: 0.7
      tools:
        - record_blood_pressure
        - query_blood_pressure
        - update_blood_pressure

  - name: blood_pressure_review_agent
    type: agent
    config:
      prompt: prompts/12-blood_pressure_review_agent.md
      model:
        provider: doubao
        name: doubao-seed-1-6-251015
        temperature: 0.7
      tools:
        - query_blood_pressure

edges:
  - from: intent_recognition
    to: blood_pressure_collect_agent
    condition: intent == "blood_pressure" && confidence >= 0.8
  
  - from: blood_pressure_collect_agent
    to: blood_pressure_review_agent
    condition: record_success == true  # 需要从state中判断是否记录成功
  
  - from: blood_pressure_review_agent
    to: END
    condition: always
```

#### 方案B：条件路由

**适用场景**：根据用户意图决定是否需要点评

**流程图**：
```
intent_recognition 
  → blood_pressure_collect_agent
  → [条件判断]
     ├─ record_success == true → blood_pressure_review_agent → END
     └─ else → END
```

**YAML配置示例**：
```yaml
edges:
  - from: blood_pressure_collect_agent
    to: blood_pressure_review_agent
    condition: record_success == true
  
  - from: blood_pressure_collect_agent
    to: END
    condition: record_success != true || intent == "query"  # 查询不需要点评
```

#### 方案C：独立使用

**适用场景**：用户只想查询数据或只想看点评

**流程图**：
```
intent_recognition 
  → [条件判断]
     ├─ intent == "record" → blood_pressure_collect_agent → blood_pressure_review_agent
     ├─ intent == "query" → blood_pressure_collect_agent (只查询)
     └─ intent == "review" → blood_pressure_review_agent (只看点评)
```

## 四、拆分影响分析

### 4.1 优点

#### 4.1.1 职责分离
- ✅ **单一职责原则**：每个Agent专注于一个任务，代码更清晰
- ✅ **易于维护**：修改数据收集逻辑不影响点评逻辑，反之亦然
- ✅ **Prompt更简洁**：每个Agent的prompt文件更短，更容易理解和维护

#### 4.1.2 灵活组合
- ✅ **可复用性**：点评Agent可以独立使用（如查看历史数据点评）
- ✅ **可扩展性**：未来可以添加其他数据收集Agent（如血糖、体重），复用点评Agent
- ✅ **流程可配置**：通过YAML配置灵活组合不同场景的流程

#### 4.1.3 性能优化
- ✅ **并行潜力**：如果未来需要，可以并行执行多个点评任务
- ✅ **缓存优化**：点评Agent可以缓存历史数据查询结果

#### 4.1.4 测试友好
- ✅ **单元测试**：可以独立测试数据收集和点评功能
- ✅ **集成测试**：可以测试不同的流程组合

### 4.2 缺点与挑战

#### 4.2.1 状态传递
- ⚠️ **状态管理**：需要在 `FlowState` 中传递数据收集的结果（如是否记录成功、记录ID等）
- ⚠️ **数据一致性**：确保点评Agent能获取到正确的数据

**解决方案**：
- 在 `FlowState` 中添加字段：`record_success`、`record_id`、`last_record_data`
- 数据收集Agent执行完成后，更新state
- 点评Agent从state中读取数据

#### 4.2.2 多轮对话
- ⚠️ **对话连续性**：拆分后，多轮对话的上下文需要在两个Agent之间传递
- ⚠️ **用户意图识别**：需要区分用户是想继续收集数据还是想看点评

**解决方案**：
- 利用LangGraph的 `checkpointer` 机制保持状态
- 在意图识别阶段区分：`record`、`query`、`review` 等子意图

#### 4.2.3 用户体验
- ⚠️ **响应延迟**：拆分后需要两次LLM调用，可能增加响应时间
- ⚠️ **对话流畅性**：如果数据收集和点评分开，可能影响对话的自然度

**解决方案**：
- 对于记录场景，采用顺序执行（方案A），自动触发点评
- 对于查询场景，可以跳过点评，或提供选项让用户选择

#### 4.2.4 代码复杂度
- ⚠️ **配置复杂度**：YAML配置变得更复杂，需要管理更多的节点和边
- ⚠️ **调试难度**：流程变长，调试时需要跟踪多个节点

**解决方案**：
- 使用流程图可视化工具（已有 `preview_service`）
- 添加详细的日志记录

### 4.3 是否适合拆分？

**结论：适合拆分，但需要谨慎设计**

**理由**：
1. ✅ **职责清晰**：数据收集和点评是两个不同的业务逻辑，拆分符合单一职责原则
2. ✅ **框架支持**：当前框架完全支持这种拆分，无需修改Python代码
3. ✅ **灵活性强**：拆分后可以灵活组合，适应不同场景
4. ⚠️ **需要设计**：需要仔细设计状态传递和流程路由逻辑

**建议**：
- **优先采用方案A（顺序执行）**：对于记录场景，自动触发点评，保持用户体验
- **渐进式拆分**：先实现方案A，验证效果后再考虑方案B和C
- **状态设计**：在 `FlowState` 中添加必要的字段，支持状态传递

## 五、LangGraph流程图配置变化

### 5.1 当前配置

```yaml
nodes:
  - name: blood_pressure_agent
    type: agent
    config:
      prompt: prompts/10-blood_pressure_agent.md
      model:
        provider: doubao
        name: doubao-seed-1-6-251015
        temperature: 0.7
      tools:
        - record_blood_pressure
        - query_blood_pressure
        - update_blood_pressure

edges:
  - from: intent_recognition
    to: blood_pressure_agent
    condition: intent == "blood_pressure" && confidence >= 0.8
```

### 5.2 拆分后配置（方案A）

```yaml
nodes:
  - name: blood_pressure_collect_agent
    type: agent
    config:
      prompt: prompts/11-blood_pressure_collect_agent.md
      model:
        provider: doubao
        name: doubao-seed-1-6-251015
        temperature: 0.7
      tools:
        - record_blood_pressure
        - query_blood_pressure
        - update_blood_pressure

  - name: blood_pressure_review_agent
    type: agent
    config:
      prompt: prompts/12-blood_pressure_review_agent.md
      model:
        provider: doubao
        name: doubao-seed-1-6-251015
        temperature: 0.7
      tools:
        - query_blood_pressure

edges:
  - from: intent_recognition
    to: blood_pressure_collect_agent
    condition: intent == "blood_pressure" && confidence >= 0.8
  
  # 记录成功后自动触发点评
  - from: blood_pressure_collect_agent
    to: blood_pressure_review_agent
    condition: record_success == true
  
  # 查询场景不需要点评，直接结束
  - from: blood_pressure_collect_agent
    to: END
    condition: intent == "query" || record_success != true
```

### 5.3 配置变化总结

| 项目 | 当前 | 拆分后 |
|------|------|--------|
| 节点数量 | 1个 | 2个 |
| Prompt文件 | 1个 | 2个 |
| 边数量 | 1条 | 3条（从intent_recognition出发） |
| 条件判断 | 简单（意图识别） | 复杂（意图+记录状态） |
| 工具配置 | 3个工具在一个Agent | 工具分散到两个Agent |

### 5.4 状态字段需求

拆分后需要在 `FlowState` 中添加以下字段（如果不存在）：

```python
# 在 backend/domain/state.py 中
class FlowState(TypedDict, total=False):
    # ... 现有字段 ...
    
    # 血压记录相关状态
    record_success: Optional[bool]  # 是否记录成功
    record_id: Optional[int]  # 记录ID
    last_record_data: Optional[Dict]  # 最后一次记录的数据
    need_review: Optional[bool]  # 是否需要点评
```

**注意**：
1. 由于 `FlowState` 使用了 `total=False`，所有字段都是可选的，理论上可以动态添加字段而不修改类型定义
2. 但为了更好的类型提示和代码可读性，建议在类型定义中添加这些字段
3. 如果采用其他方案（如通过prompt输出标记、通过工具返回结果判断），可能不需要这些字段

## 六、Python代码修改需求分析

### 6.1 用户理解验证

**用户理解**：*"在我的理解中，当前的代码框架在应对拆分时是不需要修改python代码的"*

### 6.2 验证结果

**结论：用户理解基本正确，但需要少量修改**

#### 6.2.1 无需修改的部分 ✅

1. **流程解析器** (`FlowParser`)：无需修改
   - 已经支持解析多个节点和边的配置
   - 已经支持条件边的解析

2. **图构建器** (`GraphBuilder`)：无需修改
   - 已经支持动态创建多个Agent节点
   - 已经支持条件边的构建
   - 已经支持从state中读取条件变量

3. **Agent工厂** (`AgentFactory`)：无需修改
   - 已经支持根据配置创建不同的Agent
   - 已经支持动态加载prompt和tools

4. **流程管理器** (`FlowManager`)：无需修改
   - 已经支持加载和编译多个节点的流程

#### 6.2.2 可能需要修改的部分 ⚠️

1. **状态定义** (`FlowState`)：建议添加字段（可选）
   - 建议添加 `record_success`、`record_id` 等字段，提升类型提示
   - 由于 `total=False`，也可以动态添加，但类型提示会缺失
   - **替代方案**：通过prompt让Agent在输出中标记，或通过工具返回结果判断

2. **数据收集Agent节点函数**：可能需要更新state（可选）
   - 在 `GraphBuilder._create_node_function` 中，数据收集Agent执行完成后更新state
   - 例如：`new_state["record_success"] = True`
   - **替代方案**：通过分析Agent的输出或工具调用结果来判断

3. **条件评估器** (`ConditionEvaluator`)：需要扩展（如果使用state字段）
   - 当前只支持 `intent`、`confidence`、`need_clarification` 三个字段
   - 需要在 `_build_names_dict` 方法中添加 `record_success` 等新字段
   - **替代方案**：使用 `intent` 字段区分场景（如 `intent == "record"` vs `intent == "query"`），避免使用新字段

#### 6.2.3 修改示例

**最小修改方案**（如果state字段已存在）：

```python
# 在 GraphBuilder._create_node_function 中
# 数据收集Agent节点函数
async def agent_node_action(state: FlowState) -> FlowState:
    # ... 现有代码 ...
    
    # 如果是数据收集Agent，检查是否记录成功
    if node_name == "blood_pressure_collect_agent":
        # 从工具调用结果中判断是否记录成功
        # 这里需要根据实际的工具返回结果来判断
        # 例如：检查 result 中是否包含 record_blood_pressure 的调用
        tool_calls = result.get("intermediate_steps", [])
        for tool_call in tool_calls:
            if tool_call[0].name == "record_blood_pressure":
                new_state["record_success"] = True
                new_state["last_record_data"] = tool_call[1]  # 工具返回结果
                break
    
    return new_state
```

**注意**：这个修改是可选的，可以采用以下替代方案：
1. **通过意图细分**：在意图识别阶段区分 `record`、`query`、`review` 等子意图，通过 `intent` 字段路由
2. **通过prompt标记**：让数据收集Agent在输出中标记是否成功，点评Agent根据输出判断
3. **无条件路由**：数据收集后总是进入点评Agent，由点评Agent判断是否需要点评（如查询场景直接返回）

### 6.3 最终结论

**用户理解正确度：95%**

- ✅ **核心框架无需修改**：流程解析、图构建、Agent创建等核心逻辑都支持多节点配置
- ✅ **配置驱动**：拆分主要通过YAML配置实现，符合框架设计理念
- ⚠️ **可选适配**：如果需要使用新的state字段进行条件判断，需要少量修改（约10-20行代码）
- ✅ **替代方案**：可以通过意图细分、prompt标记等方式避免修改代码

**推荐方案**：采用意图细分方式，无需修改Python代码
- 在意图识别阶段区分：`blood_pressure_record`、`blood_pressure_query`、`blood_pressure_review`
- 通过现有的 `intent` 字段进行路由，无需添加新字段
- 完全通过YAML配置实现拆分

## 七、零代码修改方案（推荐）

### 7.1 方案概述

通过**意图细分**的方式实现拆分，完全不需要修改Python代码，只需要：
1. 修改意图识别Agent的prompt，识别更细粒度的意图
2. 修改YAML配置，添加新节点和路由条件
3. 创建新的prompt文件

### 7.2 意图细分设计

将原来的 `blood_pressure` 意图细分为：
- `blood_pressure_record`：记录血压（需要点评）
- `blood_pressure_query`：查询血压（不需要点评）
- `blood_pressure_update`：更新血压（可能需要点评）
- `blood_pressure_review`：查看点评（仅点评）

### 7.3 YAML配置示例（零代码修改）

```yaml
nodes:
  - name: intent_recognition
    type: agent
    config:
      prompt: prompts/00-intent_recognition_agent.md  # 需要更新，识别细分意图
      model:
        provider: doubao
        name: doubao-seed-1-6-251015
        temperature: 0.7

  - name: blood_pressure_collect_agent
    type: agent
    config:
      prompt: prompts/11-blood_pressure_collect_agent.md
      model:
        provider: doubao
        name: doubao-seed-1-6-251015
        temperature: 0.7
      tools:
        - record_blood_pressure
        - query_blood_pressure
        - update_blood_pressure

  - name: blood_pressure_review_agent
    type: agent
    config:
      prompt: prompts/12-blood_pressure_review_agent.md
      model:
        provider: doubao
        name: doubao-seed-1-6-251015
        temperature: 0.7
      tools:
        - query_blood_pressure

edges:
  # 记录场景：收集 → 点评
  - from: intent_recognition
    to: blood_pressure_collect_agent
    condition: intent == "blood_pressure_record" && confidence >= 0.8
  
  - from: blood_pressure_collect_agent
    to: blood_pressure_review_agent
    condition: intent == "blood_pressure_record"
  
  # 查询场景：只收集，不点评
  - from: intent_recognition
    to: blood_pressure_collect_agent
    condition: intent == "blood_pressure_query" && confidence >= 0.8
  
  - from: blood_pressure_collect_agent
    to: END
    condition: intent == "blood_pressure_query"
  
  # 更新场景：收集 → 点评（可选）
  - from: intent_recognition
    to: blood_pressure_collect_agent
    condition: intent == "blood_pressure_update" && confidence >= 0.8
  
  - from: blood_pressure_collect_agent
    to: blood_pressure_review_agent
    condition: intent == "blood_pressure_update"
  
  # 仅点评场景：直接点评
  - from: intent_recognition
    to: blood_pressure_review_agent
    condition: intent == "blood_pressure_review" && confidence >= 0.8
  
  - from: blood_pressure_review_agent
    to: END
    condition: always

entry_node: intent_recognition
```

### 7.4 关键点说明

1. **意图传递**：`intent` 字段在流程执行过程中保持不变，后续节点可以通过 `intent` 判断场景
2. **条件判断**：所有条件判断都使用现有的 `intent` 字段，无需添加新字段
3. **状态传递**：历史数据通过 `history_messages` 和 `flow_msgs` 传递，点评Agent可以从中获取数据

### 7.5 优势

- ✅ **零代码修改**：完全通过配置实现
- ✅ **类型安全**：使用现有的 `intent` 字段，类型提示完整
- ✅ **易于理解**：意图清晰，流程直观
- ✅ **易于扩展**：未来可以添加更多细分意图

## 八、实施建议

### 8.1 实施步骤

1. **第一步：创建Prompt文件**
   - 创建 `11-blood_pressure_collect_agent.md`（数据收集）
   - 创建 `12-blood_pressure_review_agent.md`（数据点评）
   - 从原prompt中拆分出对应的内容

2. **第二步：更新YAML配置**
   - 在 `flow.yaml` 中添加两个新节点
   - 配置节点之间的边和条件

3. **第三步：验证状态传递**
   - 检查 `FlowState` 是否包含必要的字段
   - 如果不包含，添加字段或通过其他方式传递数据

4. **第四步：测试验证**
   - 测试数据收集流程
   - 测试自动点评流程
   - 测试查询流程（不需要点评）

5. **第五步：优化调整**
   - 根据测试结果调整prompt
   - 优化条件判断逻辑
   - 优化用户体验

### 8.2 风险控制

1. **向后兼容**：保留原 `blood_pressure_agent` 作为备份，新流程验证通过后再切换
2. **渐进式迁移**：先实现方案A（顺序执行），验证后再考虑其他方案
3. **监控告警**：添加日志和监控，及时发现拆分后的问题

### 8.3 成功标准

- ✅ 数据收集功能正常（记录、查询、更新）
- ✅ 自动点评功能正常（记录后自动触发）
- ✅ 多轮对话正常（上下文传递正确）
- ✅ 性能无明显下降（响应时间可接受）
- ✅ 用户体验良好（对话自然流畅）

## 九、总结

### 8.1 拆分可行性

**结论：高度可行**

- ✅ 框架完全支持多节点配置
- ✅ 无需修改核心Python代码（或只需少量适配）
- ✅ 通过YAML配置即可实现拆分

### 8.2 拆分价值

**结论：值得拆分**

- ✅ 职责分离，代码更清晰
- ✅ 灵活组合，适应不同场景
- ✅ 易于维护和扩展

### 8.3 注意事项

- ⚠️ 需要仔细设计状态传递机制
- ⚠️ 需要优化条件判断逻辑
- ⚠️ 需要保证用户体验不受影响

### 8.4 推荐方案

**优先采用方案A（顺序执行）**：
- 实现简单，风险低
- 用户体验好（自动触发点评）
- 符合当前业务需求

---

**文档版本**：V1.0  
**创建时间**：2025-01-27  
**作者**：AI Assistant

