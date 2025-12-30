# 问答式Agent方案设计文档

## 一、设计概述

### 1.1 设计目标

创建一个**安全边界问答Agent**（`safety_boundary_agent`），作为兜底Agent处理所有安全边界相关的问答场景，确保系统能够响应所有用户问题，并保证回复符合医疗安全边界规范。

### 1.2 设计原则

1. **兜底原则**：当其他业务Agent无法处理时，路由到安全边界Agent
2. **职责清晰**：安全边界Agent专门处理安全边界场景，不干扰正常业务流程
3. **易于维护**：安全边界规则独立管理，便于更新和维护
4. **符合架构**：使用现有的Agent创建和管理机制，最小化代码改动

### 1.3 方案选择

**采用方案A：作为兜底Agent**

- **路由优先级**：`blood_pressure` > `health_event` > `medication` > `symptom` > `safety_boundary`
- **触发条件**：当意图识别为`safety_boundary`，或无法匹配到其他业务意图时
- **优点**：确保所有问题都有回复，符合"兜底"定位
- **适用场景**：诊疗咨询、药物咨询、紧急情况、通用问答、非医学类问题等

---

## 二、架构设计

### 2.1 路由图结构

```
route节点（入口）
  ├─→ clarify_intent节点（意图不明确时）
  │     └─→ 返回route节点
  │
  └─→ Agent节点（意图明确时）
        ├─→ blood_pressure_agent
        ├─→ health_event_agent
        ├─→ medication_agent
        ├─→ symptom_agent
        ├─→ safety_boundary_agent（新增）
        └─→ 返回route节点
```

### 2.2 路由决策逻辑

**路由优先级**（从高到低）：

1. **业务意图优先**：
   - 如果用户明确提到记录/查询/更新数据（血压、健康事件、用药、症状），优先识别为对应业务意图
   - 路由到对应的业务Agent

2. **安全边界场景**：
   - 如果用户问题涉及安全边界场景，识别为`safety_boundary`意图
   - 路由到`safety_boundary_agent`

3. **意图不明确**：
   - 如果无法确定意图，识别为`unclear`
   - 路由到`clarify_intent`节点

**路由决策流程图**：

```
用户消息
  ↓
route节点（意图识别）
  ↓
意图识别结果
  ├─→ blood_pressure → blood_pressure_agent
  ├─→ health_event → health_event_agent
  ├─→ medication → medication_agent
  ├─→ symptom → symptom_agent
  ├─→ safety_boundary → safety_boundary_agent（新增）
  └─→ unclear → clarify_intent节点
```

### 2.3 Agent节点设计

**safety_boundary_agent节点**：

- **节点名称**：`safety_boundary_agent`
- **Agent键名**：`safety_boundary_agent`
- **意图类型**：`safety_boundary`
- **工具列表**：无（纯问答式，不需要工具）
- **LLM配置**：`temperature: 0.3`（较低温度，确保回复的准确性和一致性）

---

## 三、详细设计

### 3.1 意图识别设计

#### 3.1.1 新增意图类型

**文件**：`domain/router/tools/router_tools.py`

**修改位置**：`_parse_intent_result()`函数

**修改内容**：

```python
# 修改前
valid_intents = ["blood_pressure", "health_event", "medication", "symptom", "unclear"]

# 修改后
valid_intents = ["blood_pressure", "health_event", "medication", "symptom", "safety_boundary", "unclear"]
```

#### 3.1.2 路由提示词调整

**文件**：`config/prompts/local/router_intent_identification_prompt.txt`

**调整内容**：

1. **新增意图类型说明**：
   ```
   支持的意图类型：
   - blood_pressure: 血压相关（记录、查询、更新血压）
   - health_event: 健康事件相关（记录、查询、更新健康事件）
   - medication: 用药相关（记录、查询、更新用药）
   - symptom: 症状相关（记录、查询、更新症状）
   - safety_boundary: 安全边界相关（诊疗咨询、药物咨询、紧急情况、通用问答等）
   - unclear: 意图不明确
   ```

2. **新增安全边界场景识别规则**：
   ```
   如果用户问题涉及以下场景，应识别为safety_boundary意图：
   
   【诊疗相关】
   - 疾病诊断咨询（如"我这是什么病？"、"我身上长了很多红疹，是什么疾病呢？"）
   - 常规治疗方案咨询（如"高血压和糖尿病的药可以一起吃吗？"）
   - 调整用药咨询（如"降压药之前吃的氨氯地平，这次换了左氨氯地平，可以吗？"）
   - 针对性治疗方案、费用咨询（如"我有xx情况，我是否需要进行手术治疗？大概需要花费多少钱？"）
   - 健康设备推荐（如"医生可以给我推荐一款血糖仪/血压计吗？"）
   
   【药物相关】
   - 开处方请求（如"医生，你能直接帮我在线开个处方吗？"）
   - 用药剂量咨询（如"我每天吃几颗施慧达？2.5mg的"）
   - 漏服、错服、过量服咨询（如"今天早上起来忘记吃药了，现在多次一粒恩格列净片，可以吗？"）
   - 药物治疗效果对比（如"我吃阿利沙坦酯片和苯磺酸氨氯地平片2个月了，血压还是没有降下来？"）
   - 药物推荐、联合用药咨询（如"高血压吃哪种降压药效果会更好一些呀？"、"医生，血压一直降不下来，我可以把XX和XXX一起吃吗？"）
   - 药物相互作用、用药时间、频次、服药时机、服药注意事项咨询
   - 药物价格咨询（如"买XXX药大概需要多少钱？"）
   
   【危重症等紧急情况】
   - 胸痛、剧烈头痛、呼吸困难、晕厥等急性症状描述
   - 恶心、呕吐、意识障碍、视力障碍、偏瘫、抽搐等危急症状
   - 血压升高、低血压、瞳孔变化、皮肤粘膜变化等危急体征
   - 其他危急症状描述（如呕血、心动过速、心动过缓、粉红色泡沫痰等）
   
   【院内资源/政策咨询】
   - 咨询院内床位、预约手术日期、咨询挂号/加号信息
   - 咨询院内是否有某个药/某个设备、咨询院内药品价格
   - 咨询院内病例打印、咨询医疗费用、咨询医疗报销
   - 咨询院内检查进度、医生联系电话/科室电话
   
   【通用打招呼】
   - 问好&祝福、结束语
   - 服务内容及服务定位咨询（如"数字分身是什么，不是医生本人么？"）
   - 想找医生本人、质疑分身、询问分身是否是AI/大模型
   - 专门过来致谢医生
   
   【其他科室问题咨询】
   - 非心血管内科领域知识咨询
   
   【非医学类问题】
   - 跟医学领域不相关的问题
   - 未知问题（例如用户胡乱编造的问题，或者医疗健康层面不常见或你不知道的内容）
   
   【涉及儿童内容回答边界】
   - 咨询者本人未成年（≤14岁）的咨询
   - 咨询者本人已成年（＞14岁），但咨询的是儿童相关问题
   ```

3. **意图识别优先级**：
   ```
   意图识别优先级（从高到低）：
   1. 如果用户明确提到记录/查询/更新数据（血压、健康事件、用药、症状），优先识别为对应业务意图
   2. 如果用户问题涉及上述安全边界场景，识别为safety_boundary
   3. 如果无法确定，识别为unclear
   ```

### 3.2 Agent配置设计

#### 3.2.1 配置文件调整

**文件**：`config/agents.yaml`

**新增配置**：

```yaml
agents:
  # ... 其他Agent配置 ...
  
  # 安全边界问答Agent（新增）
  safety_boundary_agent:
    name: "安全边界问答Agent"
    description: "负责处理安全边界相关的问答，包括诊疗咨询、药物咨询、紧急情况处理、通用问答等"
    llm:
      # model: 不指定则使用环境变量中的 LLM_MODEL（deepseek-v3-2-251201）
      temperature: 0.3  # 较低温度，确保回复的准确性和一致性
    tools:
      # 纯问答式Agent，不需要工具
      # 如果需要查询药品说明书，可以后续添加工具
      # - query_medication_info
    
    # 提示词配置（优先使用Langfuse）
    langfuse_template: "safety_boundary_agent_prompt"  # Langfuse模版名称
    # langfuse_template_version: "v1.0"  # 可选：指定模版版本
    
    # 路由配置
    routing:
      node_name: "safety_boundary_agent"  # 路由图中的节点名称
      intent_type: "safety_boundary"       # 对应的意图类型
```

### 3.3 路由图调整

#### 3.3.1 路由图代码调整

**文件**：`domain/router/graph.py`

**调整内容**：

1. **Agent节点自动添加**：
   - 由于使用了动态Agent创建机制，`safety_boundary_agent`节点会在`create_router_graph()`中自动添加
   - 无需手动修改代码，只需确保配置文件正确

2. **路由决策逻辑**（无需修改）：
   - `route_to_agent()`函数已经支持动态路由，会根据`agent_intent_map`自动路由
   - 只要在`AgentRegistry`中注册了`safety_boundary_agent`，路由逻辑会自动生效

**验证点**：
- 确保`AgentRegistry.get_all_agents()`能够获取到`safety_boundary_agent`配置
- 确保`AgentRegistry.get_agent_node_name("safety_boundary_agent")`返回`"safety_boundary_agent"`
- 确保`AgentRegistry.get_agent_intent_type("safety_boundary_agent")`返回`"safety_boundary"`

### 3.4 提示词模板设计

#### 3.4.1 提示词模板文件

**文件**：`config/prompts/local/safety_boundary_agent_prompt.txt`（新建）

**内容来源**：基于`config/prompts/local/素材/211-安全边界规则（兜底Agent）.md`转换

**转换原则**：

1. **保留核心原则**：将7大核心原则放在提示词开头
2. **保留所有场景**：保留8大类场景的所有定义和回复话术
3. **优化结构**：将Markdown格式转换为更适合LLM理解的提示词格式
4. **明确匹配逻辑**：明确场景匹配的优先级和逻辑

**提示词结构**：

```
# 角色定义
你是一个医疗安全边界问答助手。你的职责是根据用户的问题，匹配相应的安全边界场景，并返回符合医疗安全边界规范的回复。

# 核心原则
[7大核心原则]

# 上下文信息
用户ID: {{user_id}}
会话ID: {{session_id}}
当前日期: {{current_date}}
患者基础信息: {{user_info}}
历史回话信息: {{history_msg}}

# 边界场景定义及回复话术
[8大类场景的详细定义和回复话术]

# 工作流程
1. 分析用户问题，识别涉及的安全边界场景
2. 根据场景匹配规则，选择对应的回复话术
3. 如果场景匹配多个规则，按照优先级选择（紧急情况 > 诊疗相关 > 药物相关 > 其他）
4. 生成符合安全边界的回复

# 回复风格要求
[自然、友好、人性化的回复风格要求，避免机械化列举式回复]

# 输出格式要求
[严格的JSON格式输出要求，包括session_id、response_content、reasoning_summary等字段]
```

**提示词优化建议**：

1. **场景匹配优先级**：
   - 紧急情况（危重症） > 诊疗相关 > 药物相关 > 院内资源/政策咨询 > 通用打招呼 > 其他科室问题 > 非医学类问题

2. **固定话术处理**：
   - 将固定话术提取为模板，使用占位符（如`{{symptom_name}}`）填充变量
   - LLM只需要匹配场景，然后填充模板中的变量

3. **场景特征提取**：
   - 为每个场景提取关键特征词，便于LLM快速匹配
   - 例如：紧急情况场景的关键词包括"胸痛"、"剧烈头痛"、"呼吸困难"等

4. **回复风格要求**：
   - 使用自然、口语化的表达，避免机械化列举（如"1. ... 2. ..."）
   - 像专业的医疗助手一样亲切，但保持专业性
   - 将信息自然地融入到流畅的对话中，而不是冷冰冰的规则宣读
   - 对于紧急情况，要直接、明确，但保持关怀的语气

5. **输出格式要求**：
   - 必须严格按照JSON格式返回，包含以下字段：
     - `session_id`：会话ID（必填）
     - `response_content`：回复内容（必填，直接面向用户的文本）
     - `reasoning_summary`：推理过程小结（必填，简要说明思考过程和决策依据）
     - `additional_fields`：附加字段（可选，如匹配的场景类型、安全级别等）

### 3.5 代码实现细节

#### 3.5.1 路由工具调整

**文件**：`domain/router/tools/router_tools.py`

**修改位置1**：`_parse_intent_result()`函数

```python
# 修改前（约231行）
valid_intents = ["blood_pressure", "health_event", "medication", "symptom", "unclear"]

# 修改后
valid_intents = ["blood_pressure", "health_event", "medication", "symptom", "safety_boundary", "unclear"]
```

**修改位置2**：`identify_intent()`函数的文档字符串（可选，用于文档说明）

```python
# 修改前（约276行）
支持的意图类型：
- blood_pressure: 血压相关（记录、查询、更新血压）
- health_event: 健康事件相关（记录、查询、更新健康事件）
- medication: 用药相关（记录、查询、更新用药）
- symptom: 症状相关（记录、查询、更新症状）
- unclear: 意图不明确

# 修改后
支持的意图类型：
- blood_pressure: 血压相关（记录、查询、更新血压）
- health_event: 健康事件相关（记录、查询、更新健康事件）
- medication: 用药相关（记录、查询、更新用药）
- symptom: 症状相关（记录、查询、更新症状）
- safety_boundary: 安全边界相关（诊疗咨询、药物咨询、紧急情况、通用问答等）
- unclear: 意图不明确
```

#### 3.5.2 Agent注册验证

**文件**：`domain/agents/registry.py`

**验证点**：
- 确保`AgentRegistry.get_all_agents()`能够正确加载`safety_boundary_agent`配置
- 确保`AgentRegistry.get_agent_node_name("safety_boundary_agent")`返回正确的节点名称
- 确保`AgentRegistry.get_agent_intent_type("safety_boundary_agent")`返回`safety_boundary`

**注意**：如果`AgentRegistry`使用反射机制自动加载，可能无需修改代码，只需确保配置文件正确。

#### 3.5.3 路由图验证

**文件**：`domain/router/graph.py`

**验证点**：
- 确保`create_router_graph()`能够正确创建`safety_boundary_agent`节点
- 确保`route_to_agent()`能够正确路由到`safety_boundary_agent`节点
- 确保路由映射中包含`safety_boundary_agent`

**代码检查点**（约250-270行）：
```python
# 动态创建Agent节点（在路由图创建时一次性创建）
for agent_key, agent_config in agent_registry.items():
    # ... 创建Agent实例 ...
    # 确保safety_boundary_agent能够被正确创建和添加
```

---

## 四、实施步骤

### 4.1 阶段一：创建提示词模板

**步骤**：

1. **读取源文档**：
   - 读取`config/prompts/local/素材/211-安全边界规则（兜底Agent）.md`

2. **转换格式**：
   - 将Markdown格式转换为提示词格式
   - 保留所有核心原则和场景定义
   - 优化结构，使其更适合LLM理解

3. **创建提示词文件**：
   - 创建`config/prompts/local/safety_boundary_agent_prompt.txt`
   - 写入转换后的提示词内容

4. **验证提示词**：
   - 检查提示词格式是否正确
   - 检查占位符是否正确（`{{user_id}}`、`{{session_id}}`等）
   - 检查场景定义是否完整

### 4.2 阶段二：添加Agent配置

**步骤**：

1. **修改配置文件**：
   - 在`config/agents.yaml`中添加`safety_boundary_agent`配置
   - 确保配置格式正确（YAML格式）

2. **验证配置**：
   - 使用YAML验证工具检查配置格式
   - 确保所有必需字段都存在

### 4.3 阶段三：调整路由逻辑

**步骤**：

1. **修改路由工具**：
   - 在`domain/router/tools/router_tools.py`中修改`_parse_intent_result()`函数
   - 添加`safety_boundary`到有效意图列表

2. **修改路由提示词**：
   - 在`config/prompts/local/router_intent_identification_prompt.txt`中添加安全边界场景识别规则
   - 添加意图识别优先级说明

3. **验证路由逻辑**：
   - 确保意图识别能够正确识别`safety_boundary`意图
   - 确保路由决策能够正确路由到`safety_boundary_agent`节点

### 4.4 阶段四：测试验证

**步骤**：

1. **单元测试**：
   - 测试意图识别是否正确识别安全边界场景
   - 测试路由决策是否正确路由到`safety_boundary_agent`

2. **集成测试**：
   - 测试完整流程：用户消息 → 意图识别 → 路由 → Agent执行 → 回复生成
   - 测试各种安全边界场景是否能够正确处理

3. **场景测试**：
   - 测试诊疗相关场景
   - 测试药物相关场景
   - 测试紧急情况场景
   - 测试通用打招呼场景
   - 测试非医学类问题场景

---

## 五、测试方案

### 5.1 单元测试

#### 5.1.1 意图识别测试

**测试用例**：

1. **诊疗相关场景**：
   - 输入："我这是什么病？"
   - 期望：识别为`safety_boundary`意图

2. **药物相关场景**：
   - 输入："我应该吃什么药？"
   - 期望：识别为`safety_boundary`意图

3. **紧急情况场景**：
   - 输入："我胸痛，很严重"
   - 期望：识别为`safety_boundary`意图

4. **业务意图优先**：
   - 输入："我想记录血压，今天120/80"
   - 期望：识别为`blood_pressure`意图（不是`safety_boundary`）

#### 5.1.2 路由决策测试

**测试用例**：

1. **路由到安全边界Agent**：
   - 输入：`current_intent = "safety_boundary"`
   - 期望：路由到`safety_boundary_agent`节点

2. **业务意图优先**：
   - 输入：`current_intent = "blood_pressure"`
   - 期望：路由到`blood_pressure_agent`节点（不是`safety_boundary_agent`）

### 5.2 集成测试

#### 5.2.1 完整流程测试

**测试用例**：

1. **诊疗咨询场景**：
   ```
   用户："我这是什么病？"
   期望流程：
   1. 意图识别 → safety_boundary
   2. 路由决策 → safety_boundary_agent
   3. Agent执行 → 生成符合安全边界的回复
   4. 回复内容：包含"建议您回院进行面对面的咨询"等安全边界话术
   ```

2. **紧急情况场景**：
   ```
   用户："我胸痛，很严重，感觉快死了"
   期望流程：
   1. 意图识别 → safety_boundary
   2. 路由决策 → safety_boundary_agent
   3. Agent执行 → 生成紧急情况处理回复
   4. 回复内容：包含"拨打120"、"立即停止所有活动"等紧急处理话术
   ```

3. **业务意图优先场景**：
   ```
   用户："我想记录血压，今天120/80"
   期望流程：
   1. 意图识别 → blood_pressure（不是safety_boundary）
   2. 路由决策 → blood_pressure_agent
   3. Agent执行 → 正常业务流程
   ```

### 5.3 场景测试

#### 5.3.1 安全边界场景覆盖测试

**测试场景列表**：

1. ✅ **诊疗相关**（5个场景）
2. ✅ **药物相关**（8个场景）
3. ✅ **危重症等紧急情况**（16种症状）
4. ✅ **院内资源/政策咨询**（10个场景）
5. ✅ **通用打招呼**（6个场景）
6. ✅ **其他科室问题咨询**（1个场景）
7. ✅ **非医学类问题**（2个场景）
8. ✅ **涉及儿童内容回答边界**（2个场景）

**测试方法**：
- 为每个场景设计测试用例
- 验证回复是否符合安全边界规范
- 验证回复话术是否准确

---

## 六、注意事项

### 6.1 提示词大小限制

**问题**：安全边界规则文档有1435行，转换为提示词后可能过大

**解决方案**：
1. **优化提示词结构**：提取关键信息，简化重复内容
2. **使用模板库**：将固定话术提取为模板，减少提示词大小
3. **分场景加载**：如果提示词过大，可以考虑分场景加载（但会增加复杂度）

### 6.2 场景匹配准确性

**问题**：16种危急症状场景较多，LLM可能无法准确匹配

**解决方案**：
1. **特征关键词提取**：为每个场景提取关键特征词
2. **优先级设计**：明确场景匹配的优先级（紧急情况优先）
3. **测试验证**：通过大量测试用例验证场景匹配的准确性

### 6.3 与业务Agent的冲突

**问题**：某些场景可能同时匹配业务意图和安全边界意图

**解决方案**：
1. **优先级设计**：业务意图优先于安全边界意图
2. **明确识别规则**：在路由提示词中明确区分业务意图和安全边界场景
3. **测试验证**：确保业务意图不会被误识别为安全边界意图

### 6.4 性能考虑

**问题**：安全边界Agent的提示词较大，可能影响响应速度

**解决方案**：
1. **提示词优化**：优化提示词结构，减少不必要的重复
2. **缓存机制**：如果可能，实现常见场景的回复缓存
3. **监控性能**：监控Agent的响应时间，必要时优化

---

## 七、后续优化方向

### 7.1 工具支持

**如果需要查询药品说明书**：
- 创建工具：`domain/tools/safety_boundary/query_medication_info.py`
- 在Agent配置中添加该工具
- 在提示词中说明如何使用该工具

### 7.2 兜底检查节点

**可选功能**：
- 在所有业务Agent执行后，添加安全检查节点
- 检查业务Agent的回复是否符合安全边界
- 如果不符合，修正回复或路由到安全边界Agent

### 7.3 规则引擎优化

**性能优化**：
- 使用规则引擎进行初步筛选
- 只对可疑回复进行LLM检查
- 减少LLM调用次数，提高响应速度

---

## 八、总结

### 8.1 设计要点

1. **架构设计**：采用兜底Agent方案，确保所有问题都有回复
2. **路由逻辑**：业务意图优先，安全边界场景作为兜底
3. **代码调整**：最小化改动，利用现有的动态Agent创建机制
4. **提示词设计**：基于安全边界规则文档，优化结构使其更适合LLM理解

### 8.2 实施优先级

1. 🔴 **高优先级**：创建提示词模板、添加Agent配置、调整路由逻辑
2. 🟡 **中优先级**：测试验证、性能优化
3. 🟢 **低优先级**：工具支持、兜底检查节点、规则引擎优化

### 8.3 成功标准

1. ✅ 所有安全边界场景都能正确路由到安全边界Agent
2. ✅ 安全边界Agent能够生成符合规范的回复
3. ✅ 业务意图不会被误识别为安全边界意图
4. ✅ 系统响应时间在可接受范围内

---

**文档生成时间**：2025-01-XX  
**基于代码版本**：当前代码库状态  
**参考文档**：
- `doc/设计V6.0/V6.2 Agent流程重新规划/0203-问答式Agent方案讨论.md` - 方案讨论文档
- `config/prompts/local/素材/211-安全边界规则（兜底Agent）.md` - 安全边界规则文档
- `config/agents.yaml` - Agent配置文件
- `domain/router/graph.py` - 路由图结构
- `domain/router/tools/router_tools.py` - 路由工具实现

