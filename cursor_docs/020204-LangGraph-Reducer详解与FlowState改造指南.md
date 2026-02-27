# LangGraph Reducer 详解与 FlowState 改造指南

## 文档说明

本文档详细说明：  
1）LangGraph 中 **Reducer** 是如何实现的；  
2）**Python 语法**（`Annotated`、reducer 函数）是什么、怎么用；  
3）如何对当前项目的 **FlowState** 和节点进行改造，让 `flow_msgs` 等列表字段使用 reducer。

**文档版本**：V1.0  
**创建时间**：2025-02-02

---

## 一、Reducer 是什么、解决什么问题

### 1.1 问题：多个节点写同一个 key 时怎么办？

在 LangGraph 里，每个节点通过**返回值**向 state 提交“更新”。例如节点 A 返回 `{"flow_msgs": [msg1]}`，节点 B 返回 `{"flow_msgs": [msg2]}`。若没有额外规则，框架必须决定：**同一个 key 被多次更新时，最终 state 里该 key 取谁的值？**

- **默认行为（没有 reducer）**：**覆盖**。后一次更新直接覆盖前一次。  
  例如先 A 再 B，最终 `flow_msgs == [msg2]`，`msg1` 丢了。
- **有 reducer 时**：框架不直接覆盖，而是调用你提供的 **reducer 函数**，把“当前 state 里的值”和“本次节点返回的更新”**合并**成一个新值，再写回 state。  
  例如用“列表拼接”的 reducer，先 A 再 B 会得到 `flow_msgs == [msg1, msg2]`。

所以：**Reducer 就是“如何合并同一 key 的多次更新”的规则**；实现上就是一个函数，语法上通过 **`Annotated[类型, reducer函数]`** 把这个规则绑在 state 的某个字段上。

### 1.2 Reducer 在框架里是怎么被调用的？

（概念上，不涉及 LangGraph 源码细节。）

1. 图维护一份**当前 state**（例如 `current`）。
2. 某节点执行完，返回一个**更新字典**（例如 `update = {"flow_msgs": [new_msg]}`）。
3. 对 `update` 里的每个 key（如 `flow_msgs`）：
   - 若该 key 在 state schema 里**没有**配 reducer → 直接覆盖：`current["flow_msgs"] = update["flow_msgs"]`。
   - 若该 key **有** reducer（例如 `add_messages`）→ 调用：  
     `current["flow_msgs"] = reducer(current["flow_msgs"], update["flow_msgs"])`。  
     即：**旧值**和**本次更新值**作为两个参数，返回值成为新的 state 值。

因此：**Reducer 的实现 = 你在 state 里用 `Annotated` 声明一个函数 + 框架在合并更新时调用这个函数**。你只需要写好“合并逻辑”和类型声明即可。

---

## 二、Python 语法：Annotated 与 Reducer 函数

### 2.1 `Annotated` 是什么？

`Annotated` 是 Python 标准库 `typing` 里的一个类型构造器（Python 3.9+ 在 `typing`，更早版本在 `typing_extensions`），用来给类型“挂”一些元数据，**不改变运行时类型**，但可以被工具或框架读取。

**基本形式：**

```python
from typing import Annotated

# 形式：Annotated[ 类型, 元数据1, 元数据2, ... ]
# 表示：类型还是「列表」，但带上了「用 add_messages 合并」的说明
Annotated[list[SomeMessage], add_messages]
```

- **第一个参数**：真正的类型（如 `list[BaseMessage]`）。
- **后面的参数**：元数据。LangGraph 会读取**第二个参数**（或约定的元数据），把它当作该 state key 的 **reducer 函数**。

所以：**Reducer 的语法 = 把 state 字段的类型写成 `Annotated[列表类型, reducer函数]`**。

### 2.2 在 TypedDict 里写带 Reducer 的字段

TypedDict 的 value 类型可以是任意类型，包括 `Annotated[...]`。例如：

```python
from typing import TypedDict, Annotated, List
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class FlowState(TypedDict, total=False):
    # 无 reducer：默认覆盖
    session_id: str

    # 有 reducer：更新时用 add_messages(current, update) 合并
    flow_msgs: Annotated[List[BaseMessage], add_messages]
```

这样 `flow_msgs` 的**类型**仍是 `List[BaseMessage]`，但 LangGraph 会看到 `Annotated` 里的 `add_messages`，在合并 state 时对该 key 使用 `add_messages` 而不是覆盖。

### 2.3 两种常用的 Reducer 函数

| 用途         | 函数               | 来源                     | 行为说明 |
|--------------|--------------------|--------------------------|----------|
| 列表简单追加 | `operator.add`     | 标准库 `operator`        | 对 list：`current + update`，即拼接两个列表。 |
| 消息列表追加/按 id 更新 | `add_messages` | `langgraph.graph.message` | 对消息列表：追加新消息；若消息带 id 且已存在则更新，否则追加。适合对话、人机协作。 |

**`operator.add` 示例（和 list 一起用）：**

```python
import operator

operator.add([1, 2], [3])       # -> [1, 2, 3]
operator.add(["a"], ["b", "c"]) # -> ["a", "b", "c"]
```

**在 state 里用 `operator.add`：**

```python
from typing import Annotated, TypedDict
import operator

class State(TypedDict):
    # 节点每次返回 {"logs": [新条目]}，框架会 current_logs + 新条目
    logs: Annotated[list[str], operator.add]
```

**在 state 里用 `add_messages`：**

```python
from typing import Annotated, List
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class FlowState(TypedDict, total=False):
    flow_msgs: Annotated[List[BaseMessage], add_messages]
```

- 节点只需返回 `{"flow_msgs": [new_aimessage]}`，框架会调用 `add_messages(当前列表, [new_aimessage])`，得到追加（或按 id 更新）后的新列表。

### 2.4 自己写一个 Reducer 函数（可选）

Reducer 的签名是：**两个参数，一个返回值**，且语义是“(当前值, 本次更新) → 合并后的值”。例如：

```python
def my_reducer(current: list, update: list) -> list:
    return current + update
```

用在 state 里：

```python
flow_msgs: Annotated[List[BaseMessage], my_reducer]
```

注意：**第一个参数是 state 里当前的值，第二个参数是节点这次返回的该 key 的值**；返回值会写回 state。LangGraph 会在合并时处理 `None`（如当前尚无该 key）等边界，你主要关心“两个都有值时怎么合并”。

---

## 三、本项目改造步骤

### 3.1 当前行为简述

- **`flow_msgs`**：在 `agent_creator.py` 里，节点先 `state.get("flow_msgs", [])`，再 `copy()`、`append(ai_message)`，最后 `new_state["flow_msgs"] = new_flow_msgs`。  
  即：**手动实现“在现有列表上追加”**，等价于“单节点写、默认覆盖”也能工作，但若将来多个节点都往 `flow_msgs` 追加，用 reducer 更统一、不易出错。
- **`history_messages`**：由入口处 `build_initial_state` 一次性写入，图中节点只读不写，**不需要**为追加而加 reducer；若希望“图中某节点也能追加历史消息”，再给 `history_messages` 加 reducer 即可。

下面只对 **`flow_msgs`** 做 reducer 改造；`history_messages` 保持现状。

### 3.2 改造一：在 `state.py` 里为 `flow_msgs` 声明 reducer

**文件**：`backend/domain/state.py`

**改动要点**：

1. 增加 `Annotated` 的导入（`typing` 或 `typing_extensions`）。
2. 增加 `add_messages` 的导入（`langgraph.graph.message`）。
3. 把 `flow_msgs` 的类型从 `List[BaseMessage]` 改为 `Annotated[List[BaseMessage], add_messages]`。

**改造前：**

```python
from typing import TypedDict, List, Optional, Dict, Any
from langchain_core.messages import BaseMessage, HumanMessage

class FlowState(TypedDict, total=False):
    ...
    flow_msgs: List[BaseMessage]
    ...
```

**改造后：**

```python
from typing import TypedDict, List, Optional, Dict, Any, Annotated
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph.message import add_messages

class FlowState(TypedDict, total=False):
    ...
    flow_msgs: Annotated[List[BaseMessage], add_messages]  # 追加/按 id 更新，不覆盖
    ...
```

这样，**所有**对 `flow_msgs` 的更新都会通过 `add_messages` 合并，而不是整体覆盖。

### 3.3 改造二：节点只返回“要追加的内容”，不再手动 copy + append

**文件**：`backend/domain/flows/nodes/agent_creator.py`

**当前逻辑（节选）：**

```python
flow_msgs = state.get("flow_msgs", [])
new_flow_msgs = flow_msgs.copy()
new_flow_msgs.append(ai_message)
new_state["flow_msgs"] = new_flow_msgs
```

**改造后：**

节点**不再**读取 `flow_msgs`、不再 copy/append，只把**本节点要追加的那条消息**交给 state 即可；框架会用 `add_messages(当前 flow_msgs, [ai_message])` 合并。

```python
# 将AI回复存放到 flow_msgs（由 reducer 追加，不覆盖）
ai_message = AIMessage(content=output)
new_state["flow_msgs"] = [ai_message]
```

即：**原来赋值为“整段新列表”，改为赋值为“本节点要追加的列表”**；其余对 `new_state` 的赋值（如 `edges_var`、`persistence_edges_var` 等）不变。

注意：若该节点还会往 `flow_msgs` 里写多条消息，就写成 `new_state["flow_msgs"] = [msg1, msg2]`，reducer 会把这一整列表和当前 state 里的 `flow_msgs` 用 `add_messages` 合并。

### 3.4 其他写入 `flow_msgs` 的节点

若项目里还有别的节点会往 `flow_msgs` 里追加（例如 RAG 节点、工具节点），同样改为**只返回本次要追加的列表**，例如：

```python
new_state["flow_msgs"] = [some_new_message]
```

不要再 `state.get("flow_msgs", [])` 再 copy/append 再整体赋回。

### 3.5 不改 `history_messages` 的原因

- `history_messages` 目前只在 `build_initial_state` 里被设置一次，图中节点只读。  
- 若未来有节点需要“往历史里追加一条”，再给 `history_messages` 也加上 `Annotated[List[BaseMessage], add_messages]`，并在该节点里 `return {"history_messages": [new_msg]}` 即可。

### 3.6 可选：用 `operator.add` 代替 `add_messages`

若你不需要“按 message id 更新、去重”，只要“列表简单拼接”，可以用标准库：

```python
from typing import Annotated, List
import operator
from langchain_core.messages import BaseMessage

flow_msgs: Annotated[List[BaseMessage], operator.add]
```

- 节点同样只返回 `{"flow_msgs": [ai_message]}`。
- 框架会执行 `current_flow_msgs + [ai_message]`，语义是纯追加。  
- 与 `add_messages` 的区别：不处理 message id，不做“已存在则更新”，适合简单流水线。

---

## 四、改造前后对比小结

| 项目           | 改造前                         | 改造后 |
|----------------|--------------------------------|--------|
| **state.py**   | `flow_msgs: List[BaseMessage]` | `flow_msgs: Annotated[List[BaseMessage], add_messages]` |
| **节点逻辑**   | 读 state → copy → append → 整段赋回 | 只写 `new_state["flow_msgs"] = [本节点的新消息]` |
| **多节点写**   | 若多节点都写 `flow_msgs`，后写覆盖前写 | 多节点都返回“要追加的列表”，由 reducer 合并，不会互相覆盖 |
| **Python 语法** | 无                             | 使用 `Annotated[类型, reducer函数]` 声明合并规则 |

---

## 五、完整示例代码（便于粘贴）

### 5.1 `backend/domain/state.py` 修改片段

```python
"""
流程状态定义
定义流程执行过程中的状态数据结构
"""
from typing import TypedDict, List, Optional, Dict, Any, Annotated
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph.message import add_messages


class FlowState(TypedDict, total=False):
    """
    流程状态数据结构
    用于在流程执行过程中传递数据
    """
    current_message: HumanMessage
    history_messages: List[BaseMessage]
    flow_msgs: Annotated[List[BaseMessage], add_messages]  # 使用 reducer，节点可只返回要追加的消息
    session_id: str
    token_id: Optional[str]
    trace_id: Optional[str]
    prompt_vars: Optional[Dict[str, Any]]
    edges_var: Optional[Dict[str, Any]]
    persistence_edges_var: Optional[Dict[str, Any]]
```

### 5.2 `agent_creator.py` 中相关片段修改

把“将AI回复存放到 flow_msgs”那几行从：

```python
# 将AI回复存放到 flow_msgs（流程中间消息），不存放到 history_messages
ai_message = AIMessage(content=output)
flow_msgs = state.get("flow_msgs", [])
new_flow_msgs = flow_msgs.copy()
new_flow_msgs.append(ai_message)
new_state["flow_msgs"] = new_flow_msgs
# history_messages 保持不变，不添加中间节点的输出
```

改为：

```python
# 将AI回复存放到 flow_msgs（由 add_messages reducer 追加），不存放到 history_messages
ai_message = AIMessage(content=output)
new_state["flow_msgs"] = [ai_message]
# history_messages 保持不变，不添加中间节点的输出
```

其余逻辑（如 `edges_var`、`persistence_edges_var`、`additional_fields` 等）保持不变。

---

## 六、总结

- **Reducer**：决定“同一 state key 被多次更新时如何合并”；实现 = 用 **`Annotated[类型, reducer函数]`** 声明，框架在合并时调用该函数。
- **Python 语法**：`Annotated[类型, 元数据]` 来自 `typing`（3.9+）；reducer 是“(当前值, 本次更新) → 合并结果”的函数，如 `operator.add` 或 `add_messages`。
- **项目改造**：在 `state.py` 为 `flow_msgs` 加上 `Annotated[List[BaseMessage], add_messages]`，在 `agent_creator.py`（及其他写 `flow_msgs` 的节点）改为只返回 `{"flow_msgs": [本节点的新消息]}`，由框架负责合并。

按上述修改后，多节点往 `flow_msgs` 追加时不会互相覆盖，且符合 LangGraph 推荐的消息列表用法。

---

**文档生成时间**：2025-02-02  
**对应代码**：`backend/domain/state.py`、`backend/domain/flows/nodes/agent_creator.py`
