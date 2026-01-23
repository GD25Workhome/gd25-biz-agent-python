# query_user_info_node_func 设计文档

## 一、需求概述

### 1.1 功能目标

实现一个用户信息查询节点 `query_user_info_node_func`，用于在流程中自动查询用户的健康数据（如血压信息），并将查询结果存储到流程状态中，供后续节点使用。

### 1.2 核心需求

1. **简化设计**：当前采用硬编码方式，直接处理 `blood_pressure` 查询，避免过度设计
2. **时间范围处理**：工具内部已处理时间范围（默认查询最近14天），节点层直接调用工具接口
3. **数据存储**：查询结果存储到 `FlowState` 的 `prompt_vars` 中，使用 `blood_pressure_list` 字段名
4. **配置驱动**：通过 `flow.yaml` 配置查询类型列表，节点检查是否包含 `blood_pressure`

### 1.3 使用场景

- 在记录数据后，自动查询用户的历史血压数据，用于数据分析和对比
- 在回答用户问题前，预先加载用户血压数据，提升回答准确性

**注意**：当前仅支持血压数据查询，采用简化设计。后续如需支持更多查询类型，再考虑引入扩展机制。

## 二、架构设计

### 2.1 节点位置

```
backend/domain/flows/implementations/
  └── query_user_info_node.py  # 新增节点实现
```

### 2.2 类继承关系

```python
QueryUserInfoNode(BaseFunctionNode)
  ├── get_key() -> str  # 返回 "query_user_info_node_func"
  └── execute(state: FlowState) -> FlowState  # 执行查询逻辑
```

### 2.3 数据流设计

```
FlowState (输入)
  ├── token_id: str  # 用户ID
  ├── prompt_vars: Dict  # 存储查询结果
  └── edges_var: Dict  # 可能包含时间信息
  
  ↓
  
QueryUserInfoNode.execute()
  ├── 检查配置：是否包含 blood_pressure（硬编码检查）
  ├── 调用工具辅助函数：query_blood_pressure_raw()（工具内部处理 token_id 和时间范围）
  └── 存储结果到 state.prompt_vars["blood_pressure_list"]
  
  ↓
  
FlowState (输出)
  ├── prompt_vars["blood_pressure_list"]: List[Dict]  # 血压数据列表（多条历史记录）
  └── 其他字段保持不变
```

## 三、详细设计

### 3.1 节点配置结构

在 `flow.yaml` 中的配置示例：

```yaml
- name: query_user_info_node
  type: function
  config:
    function_key: "query_user_info_node_func"
    query_list:
      - blood_pressure
      # 后续可扩展：
      # - medication
      # - symptom
      # - health_event
```

### 3.2 状态数据结构

#### 3.2.1 输入状态（FlowState）

```python
{
    "token_id": "user_123",  # 用户ID
    "prompt_vars": {},  # 可能已有其他数据
    "edges_var": {},  # 可能包含时间信息
    # ... 其他字段
}
```

#### 3.2.2 输出状态（FlowState）

```python
{
    "token_id": "user_123",
    "prompt_vars": {
        "blood_pressure_list": [  # 查询结果（多条历史记录）
            {
                "systolic": 120,
                "diastolic": 80,
                "heart_rate": 72,
                "record_time": "2024-01-15 10:30:00",
                "notes": "正常"
            },
            # ... 更多记录
        ],
        # ... 其他已有数据
    },
    # ... 其他字段保持不变
}
```

### 3.3 核心实现逻辑

#### 3.3.1 配置读取

```python
# 简化设计：直接检查配置中是否包含 blood_pressure
# 配置通过 state 的元数据传递，或通过类属性存储
has_blood_pressure = self._has_blood_pressure_in_config(state)
if has_blood_pressure:
    # 硬编码：直接调用血压查询接口
    blood_pressure_data = await self._query_blood_pressure()
```

**注意**：由于 `BaseFunctionNode.execute()` 只接收 `state` 参数，配置信息需要通过以下方式之一获取：
1. 从 `state` 的元数据中读取（如果流程系统支持）
2. 通过类属性存储配置（静态配置）

**当前实现**：简化设计，直接检查配置中是否包含 `blood_pressure`，如果包含则调用血压查询接口（硬编码）。不引入 QUERY_HANDLERS 等扩展机制，避免过度设计。

#### 3.3.2 时间范围处理

```python
# 注意：Repository 层的 get_recent_by_user_id 方法已经处理了时间范围计算
# 默认查询最近14天的数据，无需在节点层计算时间
# 只需要传入 user_id 即可，Repository 会自动使用默认的14天范围
```

#### 3.3.3 查询工具调用

```python
from backend.domain.tools.blood_pressure_tool import query_blood_pressure_raw

# 直接调用工具的辅助函数，获取原始数据
# 工具内部已处理 token_id 获取（通过 get_token_id()）
# 工具内部已处理时间范围（默认14天）
records = await query_blood_pressure_raw()
# 不传入任何参数，使用默认的14天范围，token_id 从上下文自动获取
```

**说明**：
- 在 `blood_pressure_tool.py` 中添加一个内部辅助函数 `query_blood_pressure_raw()`
- 该函数复用 `query_blood_pressure` 工具的逻辑，但返回原始数据对象而不是格式化字符串
- 节点中直接调用这个辅助函数，利用工具已有的 token_id 获取和时间处理逻辑
- 这样既复用了工具的逻辑，又能获取原始数据

#### 3.3.4 数据存储

```python
# 确保 prompt_vars 存在
if "prompt_vars" not in new_state:
    new_state["prompt_vars"] = {}

# 存储查询结果（使用 blood_pressure_list 表示多条历史记录）
new_state["prompt_vars"]["blood_pressure_list"] = blood_pressure_data
```

### 3.4 简化设计说明

**设计原则**：当前采用简化设计，避免过度设计。

- **硬编码处理**：直接检查配置中是否包含 `blood_pressure`，如果包含则调用血压查询接口
- **不引入扩展机制**：暂时不引入 QUERY_HANDLERS 等扩展机制，因为模块刚开始设计，部分设计还未定稿
- **后续扩展**：当需要支持更多查询类型时，再考虑引入统一的扩展机制

## 四、实现细节

### 4.1 节点类实现

```python
"""
用户信息查询节点实现
"""
import logging
from typing import List, Dict, Any

from backend.domain.state import FlowState
from backend.domain.flows.nodes.base_function import BaseFunctionNode
from backend.domain.tools.blood_pressure_tool import query_blood_pressure_raw

logger = logging.getLogger(__name__)


class QueryUserInfoNode(BaseFunctionNode):
    """用户信息查询节点"""
    
    @classmethod
    def get_key(cls) -> str:
        """返回节点的唯一标识key"""
        return "query_user_info_node_func"
    
    def _has_blood_pressure_in_config(self, state: FlowState) -> bool:
        """
        检查配置中是否包含 blood_pressure
        
        注意：由于 execute 方法只接收 state，配置需要通过以下方式之一获取：
        1. 从 state 的元数据中读取（如果流程系统支持）
        2. 通过类属性存储（静态配置）
        
        当前实现：从 state 中读取（如果流程系统在状态中存储了节点配置）
        或使用默认配置
        
        Args:
            state: 流程状态
            
        Returns:
            是否包含 blood_pressure 查询
        """
        # 方案1：从 state 中读取（如果流程系统支持）
        node_config = state.get("_node_config", {})
        query_list = node_config.get("query_list", [])
        
        if query_list:
            return "blood_pressure" in query_list
        
        # 方案2：默认配置（如果无法从 state 读取，默认查询血压）
        return True
    
    async def _query_blood_pressure(
        self
    ) -> List[Dict[str, Any]]:
        """
        查询血压数据（返回原始数据）
        
        Returns:
            血压记录列表（不包含 id 字段）
            
        注意：
        - 直接调用 query_blood_pressure 工具的辅助函数
        - 工具内部已处理 token_id 获取（通过 get_token_id()）
        - 工具内部已处理时间范围（默认14天）
        - 返回原始数据而不是格式化字符串
        """
        from backend.domain.tools.blood_pressure_tool import query_blood_pressure_raw
        
        # 调用工具的辅助函数，获取原始数据
        # 不传入任何参数，使用默认的14天范围，token_id 从上下文自动获取
        records = await query_blood_pressure_raw()
        
        # 转换为字典列表（只保留必要字段，不包含 id）
        result = []
        for record in records:
            result.append({
                "systolic": record.systolic,
                "diastolic": record.diastolic,
                "heart_rate": record.heart_rate,
                "record_time": record.record_time.isoformat() if record.record_time else None,
                "notes": record.notes
            })
        
        logger.info(f"查询血压数据成功: count={len(result)}")
        return result
    
    async def execute(self, state: FlowState) -> FlowState:
        """
        执行用户信息查询节点
        
        功能：
        1. 检查配置中是否包含 blood_pressure
        2. 如果包含，调用血压查询接口（硬编码）
        3. 将查询结果存储到 state.prompt_vars 中
        
        Args:
            state: 流程状态对象
            
        Returns:
            FlowState: 更新后的状态对象
        """
        try:
            # 1. 检查配置中是否包含 blood_pressure
            if not self._has_blood_pressure_in_config(state):
                logger.info("配置中不包含 blood_pressure，跳过用户信息查询")
                return state
            
            # 2. 执行查询
            new_state = state.copy()
            if "prompt_vars" not in new_state:
                new_state["prompt_vars"] = {}
            
            # 3. 硬编码处理：直接调用血压查询接口
            blood_pressure_data = await self._query_blood_pressure()
            new_state["prompt_vars"]["blood_pressure_list"] = blood_pressure_data
            logger.info(f"查询血压数据完成: count={len(blood_pressure_data)}")
            
            logger.info("用户信息查询完成")
            return new_state
            
        except Exception as e:
            logger.error(f"用户信息查询节点执行失败: {e}", exc_info=True)
            # 降级：返回原状态，不阻塞流程
            return state
```

### 4.2 配置读取问题解决方案

由于 `BaseFunctionNode.execute()` 只接收 `state` 参数，无法直接访问节点配置。

**采用方案**：参考 Agent 节点的做法，在 `FunctionNodeCreator` 中将配置存储到节点实例的属性中。

#### 实现方式

**在 `FunctionNodeCreator.create()` 中**：

```python
# 实例化节点
node_instance = node_class()

# 将配置存储到节点实例的属性中（参考 Agent 节点的设计模式）
node_instance._config = config

# 返回节点的execute方法
return node_instance.execute
```

**在节点的 `execute()` 方法中**：

```python
async def execute(self, state: FlowState) -> FlowState:
    # 从实例属性中读取配置
    config = getattr(self, "_config", {})
    query_list = config.get("query_list", [])
    
    # 检查是否包含 blood_pressure
    if "blood_pressure" in query_list:
        # 执行查询...
        ...
```

#### 设计优势

1. **与现有设计一致**：Agent 节点也采用类似方式（通过闭包访问配置）
2. **无需修改接口**：不需要修改 `BaseFunctionNode` 接口
3. **实现简单**：只需在创建器中添加一行代码
4. **配置在创建时读取**：配置在节点创建时（启动时）读取，运行时直接访问

#### 其他方案（暂不考虑）

**方案A：从 state 元数据读取**
- 需要流程系统支持将配置注入到 state
- 当前流程系统不支持此方式
- **状态**：暂不考虑

**方案B：修改 BaseFunctionNode 接口**
- 需要修改基类接口，影响所有 Function 节点
- 改动较大，不符合当前简化设计原则
- **状态**：暂不考虑

### 4.3 时间范围处理

**注意**：`query_blood_pressure` 工具内部已经处理了时间范围：
- 默认查询最近14天的数据（`days=None` 时使用默认值14）
- 工具内部调用 Repository 的 `get_recent_by_user_id` 方法
- 时间范围限制：最多查询14天内的数据

因此，节点层无需计算时间，直接调用工具的辅助函数即可：

```python
# 调用工具的辅助函数，不传入任何参数
# 工具内部会处理 token_id 获取（通过 get_token_id()）和时间范围（默认14天）
records = await query_blood_pressure_raw()
```

### 4.4 工具辅助函数实现

**需要在 `blood_pressure_tool.py` 中添加辅助函数**：

```python
async def query_blood_pressure_raw(
    days: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> List[BloodPressureRecord]:
    """
    查询血压记录（返回原始数据对象）
    
    这是 query_blood_pressure 工具的内部辅助函数，
    返回原始数据对象而不是格式化字符串。
    
    Args:
        days: 查询天数（默认14天，最大14天）
        start_date: 开始日期（格式：YYYY-MM-DD，可选）
        end_date: 结束日期（格式：YYYY-MM-DD，可选，默认为当前日期）
        
    Returns:
        血压记录对象列表（BloodPressureRecord）
    """
    # 从运行时上下文获取 token_id
    token_id = get_token_id()
    if not token_id:
        logger.warning("无法获取用户ID，返回空列表")
        return []
    
    # 获取数据库会话并执行操作
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            repo = BloodPressureRepository(session)
            
            # 解析日期参数（支持多种格式）
            parsed_start_date = None
            parsed_end_date = None
            
            if start_date:
                parsed_start_date = parse_datetime(start_date)
                if parsed_start_date is None:
                    logger.warning(f"开始日期格式不正确: {start_date}")
                    return []
            
            if end_date:
                parsed_end_date = parse_datetime(end_date)
                if parsed_end_date is None:
                    logger.warning(f"结束日期格式不正确: {end_date}")
                    return []
                # 如果只提供了日期（没有时间），设置为当天的结束时间（23:59:59）
                if parsed_end_date.hour == 0 and parsed_end_date.minute == 0 and parsed_end_date.second == 0:
                    parsed_end_date = parsed_end_date.replace(hour=23, minute=59, second=59)
            
            # 确定查询天数（默认14天，最大14天）
            query_days = min(days or 14, 14)
            
            # 查询记录
            records = await repo.get_recent_by_user_id(
                user_id=token_id,
                days=query_days,
                start_date=parsed_start_date,
                end_date=parsed_end_date
            )
            await session.commit()
            
            logger.info(f"查询血压记录成功 (user_id={token_id}, count={len(records)})")
            return records
            
        except Exception as e:
            await session.rollback()
            logger.error(f"查询血压记录失败 (user_id={token_id}): {e}", exc_info=True)
            return []
```

**然后修改 `query_blood_pressure` 工具，复用辅助函数**：

```python
@register_tool
async def query_blood_pressure(
    days: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> str:
    """
    查询血压记录（返回格式化字符串）
    """
    # 调用辅助函数获取原始数据
    records = await query_blood_pressure_raw(days=days, start_date=start_date, end_date=end_date)
    
    # 格式化输出
    if not records:
        return "您在此时间段内没有血压记录。"
    
    lines = [f"共找到 {len(records)} 条血压记录：\n"]
    for i, record in enumerate(records, 1):
        line = f"{i}. "
        if record.record_time:
            line += f"{record.record_time.strftime('%Y-%m-%d %H:%M')} - "
        else:
            line += f"{record.created_at.strftime('%Y-%m-%d %H:%M')} - "
        line += f"收缩压 {record.systolic} mmHg，舒张压 {record.diastolic} mmHg"
        if record.heart_rate:
            line += f"，心率 {record.heart_rate} 次/分钟"
        if record.notes:
            line += f"，备注：{record.notes}"
        lines.append(line)
    
    return "\n".join(lines)
```

这样设计的好处：
1. **复用工具逻辑**：直接调用工具方法，复用已有的 token_id 获取和时间处理逻辑
2. **简化节点逻辑**：节点层不需要关心 token_id 获取和时间计算
3. **统一处理逻辑**：所有查询逻辑集中在工具层，保持一致性
4. **易于维护**：如果需要修改查询逻辑，只需修改工具层

### 4.5 错误处理

1. **用户ID缺失**：工具内部会处理，返回空列表，节点层无需检查
2. **查询失败**：工具内部会记录错误日志并返回空列表，节点层直接使用结果
3. **未知查询类型**：记录警告日志，跳过该类型
4. **数据转换异常**：捕获异常，记录错误日志，返回空列表，不阻塞流程

## 五、使用示例

### 5.1 流程配置

```yaml
# config/flows/medical_agent_v4_2/flow.yaml
nodes:
  # 用户信息查询节点
  - name: query_user_info_node
    type: function
    config:
      function_key: "query_user_info_node_func"
      query_list:
        - blood_pressure
```

### 5.2 数据存储说明

节点执行完成后，血压数据会存储到 `state.prompt_vars["blood_pressure_list"]` 中，供后续节点使用。

数据格式：
```python
prompt_vars["blood_pressure_list"] = [
    {
        "systolic": 120,
        "diastolic": 80,
        "heart_rate": 72,
        "record_time": "2024-01-15T10:30:00",
        "notes": "正常"
    },
    # ... 更多记录
]
```

后续节点（如 Agent 节点）可以通过 `prompt_vars` 访问这些数据，在提示词中使用。

## 六、扩展计划

**当前状态**：采用简化设计，硬编码处理 `blood_pressure` 查询，避免过度设计。

### 6.1 后续扩展方向（待设计定稿后）

当模块设计稳定后，可以考虑以下扩展：

1. **支持更多查询类型**：
   - 引入统一的查询类型处理机制（如 QUERY_HANDLERS）
   - 支持 medication、symptom、health_event 等查询类型

2. **支持自定义时间范围**：
   - 在配置中支持自定义查询天数
   - 支持指定开始和结束日期

3. **支持数据过滤和聚合**：
   - 支持按条件过滤查询结果
   - 支持数据聚合统计

**注意**：当前不实现这些扩展功能，保持代码简洁，避免过度设计。

## 七、注意事项

### 7.1 配置读取方式

配置通过 `FunctionNodeCreator` 在节点创建时存储到节点实例的属性中（`_config`），节点运行时通过 `getattr(self, "_config", {})` 访问配置。

### 7.2 数据格式一致性

确保查询返回的数据格式与后续节点使用的格式一致。数据存储到 `prompt_vars["blood_pressure_list"]` 中，格式为字典列表，包含 `systolic`、`diastolic`、`heart_rate`、`record_time`、`notes` 字段。

### 7.3 性能考虑

1. **查询优化**：对于大量数据，考虑添加分页或限制查询数量
2. **缓存机制**：如果同一流程中多次查询相同数据，考虑缓存
3. **异步查询**：工具调用是异步的，不会阻塞流程执行

### 7.4 错误处理策略

采用"优雅降级"策略：
- 查询失败不影响流程继续执行
- 返回空结果而不是抛出异常
- 记录详细日志便于排查问题

### 7.5 工具辅助函数实现

**重要**：在实现节点之前，需要先在 `blood_pressure_tool.py` 中添加 `query_blood_pressure_raw()` 辅助函数：
- 该函数复用 `query_blood_pressure` 工具的逻辑
- 但返回原始数据对象（`List[BloodPressureRecord]`）而不是格式化字符串
- 节点中调用这个辅助函数，利用工具已有的 token_id 获取和时间处理逻辑
- 这样既复用了工具的逻辑，又能获取原始数据供节点使用

## 八、总结

本设计文档详细描述了 `query_user_info_node_func` 节点的设计思路和实现方案。该节点具有以下特点：

1. **简化设计**：采用硬编码方式处理 `blood_pressure` 查询，避免过度设计
2. **配置驱动**：通过 `flow.yaml` 配置查询类型列表
3. **工具复用**：直接调用工具的辅助函数，复用已有的 token_id 获取和时间处理逻辑
4. **错误容错**：完善的错误处理，不影响流程执行

**设计原则**：当前采用简化设计，当模块设计稳定后再考虑引入扩展机制。实现时需要注意配置读取方式和数据格式一致性，确保节点能够正确集成到现有流程系统中。

---

**文档生成时间**：2025-01-21  
**设计版本**：V1.0  
**对应代码路径**：`backend/domain/flows/implementations/query_user_info_node.py`
