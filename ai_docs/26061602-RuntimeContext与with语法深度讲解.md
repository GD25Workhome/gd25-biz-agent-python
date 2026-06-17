# RuntimeContext 与 `with` 语法深度讲解

> 本文从 **零基础** 讲起：先说明 `with open` 是什么，再说明项目里的 `with RuntimeContext`。  
>
> 常见困惑：  
> **① `with` / `with open` 到底是什么？**  
> **② 内层没有嵌套 `with` 了，外层还需要吗？**  
> **③ 项目里为什么要用 `with RuntimeContext`？**  
>
> 结合本项目 `backend/domain/tools/context.py` 与 `backend/app/api/routes/chat.py` 说明。

---

## 零、从零开始：`with` 和 `with open` 是什么

> **如果你从未用过 `with open`，请整节读完再往下看。** 后面所有 `with RuntimeContext` 的讲解，都建立在本节的同一套机制上。

### 0.1 先理解：程序读文件时发生了什么

计算机里的「文件」在程序看来，往往要先 **打开（open）** 才能读或写；用完之后应该 **关闭（close）**。

可以把它想成：

- **open** = 向操作系统「借」一个文件通道
- **read / write** = 通过这个通道操作内容
- **close** = 把通道还回去

如果不 close，可能出现：

- 文件被占用，别的程序改不了
- 内存或系统资源泄漏
- 写入的内容还没真正刷到磁盘

所以：**打开文件后，必须保证最终会关闭**——这就是 `with` 要解决的核心问题。

---

### 0.2 最原始的写法（没有 `with`）

```python
# 1. 打开文件，得到文件对象 f
f = open("note.txt", "r", encoding="utf-8")

# 2. 读取全部内容
content = f.read()
print(content)

# 3. 手动关闭
f.close()
```

逐行说明：

| 代码 | 含义 |
|------|------|
| `open("note.txt", "r", encoding="utf-8")` | 打开名为 `note.txt` 的文件；`"r"` 表示只读；`encoding` 指定用 UTF-8 解码中文 |
| `f.read()` | 把文件从头到尾读成一个字符串 |
| `f.close()` | 关闭文件，释放资源 |

**问题：** 如果在 `read()` 和 `close()` 之间程序 **报错**（抛异常），`close()` 可能永远执行不到：

```python
f = open("note.txt", "r", encoding="utf-8")
content = f.read()
result = 1 / 0          # 这里报错！后面的 close 不会执行
f.close()               # 永远到不了
```

---

### 0.3 稍好一点的写法：`try` / `finally`

程序员发现「无论如何都要 close」，就写成：

```python
f = open("note.txt", "r", encoding="utf-8")
try:
    content = f.read()
    print(content)
finally:
    f.close()   # 无论 try 里是否报错，finally 都会执行
```

这比上一版安全，但 **每次读写文件都要写一长串 try/finally**，很重复。

---

### 0.4 `with open`：Python 提供的「自动帮你 close」的语法糖

```python
with open("note.txt", "r", encoding="utf-8") as f:
    content = f.read()
    print(content)
# 执行到这里时，文件已经自动 close 了，不需要写 f.close()
```

**这就是 `with open`。** 它做的事，本质上等价于上一节的 `try/finally + close`，但更短、更不容易忘。

---

### 0.5 把这一行拆开看（非常重要）

```python
with open("note.txt", "r", encoding="utf-8") as f:
    content = f.read()
```

可以拆成 5 个部分理解：

| 部分 | 是什么 | 作用 |
|------|--------|------|
| `with` | 关键字 | 表示「进入一段需要自动清理的代码块」 |
| `open("note.txt", "r", encoding="utf-8")` | 函数调用 | 打开文件，返回一个 **文件对象** |
| `as f` | 别名 | 把打开后的文件对象起名叫 `f`，只在 `with` 块里用 |
| 冒号 `:` 后面的 **缩进块** | 你要执行的代码 | 在这里读、写、处理文件 |
| （隐式）块结束 | Python 自动调用清理 | 相当于自动 `f.close()` |

**缩进 = 作用域：**

```python
with open("note.txt") as f:
    content = f.read()    # 这两行属于 with 块，在块内 f 可用
    print(content)
print("块外")             # 块已结束，文件已关闭；一般不应再使用 f
```

---

### 0.6 `with` 在幕后实际调用了什么？（用生活例子理解）

`open(...)` 返回的对象支持两个特殊方法（你平时不用手写，Python 会自动调）：

| 方法 | 何时调用 | 类比 |
|------|----------|------|
| `__enter__()` | 进入 `with` 块 **之前** | 进房间：拿钥匙、开灯 |
| `__exit__(...)` | 离开 `with` 块 **之后**（含报错时） | 出房间：关灯、还钥匙 |

对 `open` 来说：

- `__enter__` ≈ 文件已经打开好，把 `f` 交给你用
- `__exit__` ≈ 调用 `f.close()` 关文件

用伪代码表示 Python 帮你做的事：

```python
# 你写的：
with open("note.txt") as f:
    content = f.read()

# Python 大致等价于：
_f_manager = open("note.txt")
f = _f_manager.__enter__()
try:
    content = f.read()
finally:
    _f_manager.__exit__(...)   # 里面会 close 文件
```

**记住一句话：**

> **`with` = 「进入时准备资源，离开时无论成功还是失败都自动清理」。**

---

### 0.7 `open` 的常见参数（知道即可）

```python
open(文件路径, 模式, encoding=编码)
```

| 模式 | 含义 |
|------|------|
| `"r"` | 只读（文件必须存在） |
| `"w"` | 写入（不存在则创建；存在则 **清空** 再写） |
| `"a"` | 追加（在文件末尾接着写） |

本项目业务代码里很少直接 `open` 文件（更多是数据库、HTTP、LangGraph），但 **`with` 的机制和读文件完全一样**。

---

### 0.8 完整小例子：读、写、异常

**读文件：**

```python
with open("user.txt", "r", encoding="utf-8") as f:
    name = f.read().strip()
print(f"用户名：{name}")
```

**写文件：**

```python
with open("log.txt", "a", encoding="utf-8") as f:
    f.write("一条日志\n")
```

**块内报错也会 close：**

```python
with open("note.txt", "r", encoding="utf-8") as f:
    content = f.read()
    raise ValueError("故意报错")
# 即使报错，文件仍会被 close
```

---

### 0.9 `with` 不只用于文件

只要某个对象实现了 `__enter__` 和 `__exit__`，就可以写 `with 某对象:`。

| 常见用法 | 自动清理的是什么 |
|----------|------------------|
| `with open(...)` | 关闭文件 |
| `with lock:`（线程锁） | 释放锁 |
| `with RuntimeContext(...):`（本项目） | 恢复 ContextVar 里的 token_id 等 |

所以：**`with open` 只是 `with` 最常见的一个例子**，不是 `with` 的全部含义。

---

### 0.10 和本项目的关系（先建立桥梁）

```python
# 文件场景：with 保证 close
with open("note.txt") as f:
    data = f.read()

# 本项目：with 保证 ContextVar 被 reset
with RuntimeContext(token_id="U123"):
    await graph.ainvoke(...)
```

| | `with open` | `with RuntimeContext` |
|---|-------------|------------------------|
| 管理的「资源」 | 文件句柄 | 当前请求的用户 ID 等上下文 |
| 进入时 | 打开文件 | `set(token_id=...)` |
| 退出时 | `close()` | `reset()` 恢复旧值 |
| 为什么要用 | 防止忘记关文件 | 防止忘记恢复上下文、并发串数据 |

**你现在只需要先记住：**  
项目里的 `with RuntimeContext`，和 `with open` **是同一类语法**；区别只是「清理的对象」从文件变成了「请求上下文」。

---

## 一、先给直接答案（RuntimeContext 专题）

### 问题 1：内层不再嵌套 `with`，外层还需要吗？

**需要。** 除非你在入口用等价方式做了「设置 + 保证恢复」两件事。

`with RuntimeContext(...)` 的核心目的**不是**「支持多层嵌套」，而是：

| 作用 | 说明 |
|------|------|
| **进入时写入** | 把 `token_id` / `session_id` / `trace_id` 放进当前协程的 `ContextVar` |
| **退出时恢复** | 无论正常返回还是抛异常，都 `reset` 回进入前的值 |

即使全项目只有 **一处** `with RuntimeContext`，没有内层再包一层，它仍然负责 **生命周期管理**。  
没有它，你就要自己写 `set` + `try/finally` + `reset(token)`，且容易漏掉异常路径。

### 问题 2：缺哪块基础？

若 **`with open` 也不熟悉**，请先读本文 **「零、从零开始」** 整节。

若已理解 `with open`，仍不懂 `RuntimeContext`，通常是缺下面 **4 块连起来的知识**：

1. **隐式上下文传递**（为什么不层层传参）
2. **`contextvars`**（协程里「当前请求是谁」存哪）
3. **上下文管理器协议**（`with` 在这里 ≠ 关文件）
4. **async + 框架回调**（`await graph.ainvoke` 里 Tool 怎么还能读到值）

下面按「从易到难」展开；每节都对照你项目里的真实代码。

---

## 二、从 `with open` 到 `with RuntimeContext`：同一语法，不同职责

> 若上一节「零」已读完，这里就是把同一套 `with` 机制映射到本项目。

### 2.1 复习：`with open` 在做什么

```python
with open("a.txt") as f:
    data = f.read()
# 离开 with 块后，文件自动 close
```

Python 做的事（与「零、0.6」相同）：

1. 调用 `open(...).__enter__()` → 得到资源 `f`
2. 执行 `with` 块里的代码
3. 调用 `__exit__()` → **释放资源**（正常或异常都会走）

### 2.2 本项目的 `with RuntimeContext`

```python
with RuntimeContext(
    token_id=request.token_id,
    session_id=request.session_id,
    trace_id=request.trace_id,
):
    result = await graph.ainvoke(initial_state, config)
# 离开 with 块后，ContextVar 被 reset
```

对应实现（简化理解）：

```python
def __enter__(self):
    # 写入，并保存「旧值的凭证 token」
    self._tokens.append(('token_id', _token_id_context.set(self.token_id)))
    ...

def __exit__(self, exc_type, exc_val, exc_tb):
    # 用 token 恢复进入 with 之前的状态
    for name, token in reversed(self._tokens):
        _token_id_context.reset(token)
```

**对比：**

| | `with open` | `with RuntimeContext` |
|---|-------------|------------------------|
| 管理的资源 | 文件句柄 | **当前协程上下文里的 3 个 ID** |
| `__enter__` | 打开文件 | `ContextVar.set(...)` |
| `__exit__` | `close()` | `ContextVar.reset(token)` |
| 为何必须用 `with` | 防止忘记 close | 防止忘记 reset / 异常时泄漏 |

所以：**这里的 `with` 是「上下文管理器模式」，不是「嵌套语法糖」。**

---

## 三、没有内层 `with` 时，不用 `with` 行不行？

### 3.1 方案 A：入口直接 `set_*()`，不 `reset`

```python
set_token_id(request.token_id)
set_session_id(request.session_id)
set_trace_id(request.trace_id)
result = await graph.ainvoke(initial_state, config)
# 没有 reset
```

在 FastAPI「一请求一 Task、Handler 结束 Task 即销毁」的常见部署下，**有时看起来也能跑**，但这是不稳妥的：

- 若 `ainvoke` **中途抛异常**，后面若还有代码依赖「干净的上下文」，会读到脏值
- 同一 Task 内若还有后续逻辑（中间件、日志、重试），可能误用上一段设置的 ID
- 单元测试里连续跑多个用例时，更容易串数据
- 将来若在**同一请求**里嵌套两次不同用户的操作，无法恢复

### 3.2 方案 B：手动 `try/finally`（等价于 `with`，但更啰嗦）

```python
tokens = []
try:
    if request.token_id:
        tokens.append(_token_id_context.set(request.token_id))
    result = await graph.ainvoke(initial_state, config)
finally:
    for token in reversed(tokens):
        _token_id_context.reset(token)
```

`RuntimeContext` 就是把这段 **封装成可复用的上下文管理器**。  
所以：**不是「有没有嵌套 with」决定要不要 with，而是「要不要自动 set/reset」决定。**

### 3.3 方案 C：不用 ContextVar，层层传参

理论上可以，但在你的架构里成本高：

```
chat() → graph.ainvoke → node → Agent → LangChain → Tool
```

Tool 由 **LLM + 框架** 按 JSON 参数调用，不会自动帮你把 `token_id` 塞进 Tool 参数。  
要么改 Tool 签名（LLM 不应决定 token_id），要么改框架层注入——当前选的是 **ContextVar 隐式传递**，入口就必须有一处「写入上下文」，`with` 是最干净的写入+清理方式。

---

## 四、缺的基础知识 ①：显式传参 vs 隐式上下文

### 4.1 显式传参（直觉友好）

```python
async def chat(request):
    await run_graph(request.token_id, ...)

async def run_graph(token_id, ...):
    await call_tool(token_id, ...)
```

调用链上**每个函数签名都带 `token_id`**，读代码就能追踪。

### 4.2 隐式上下文（框架型项目常用）

```python
async def chat(request):
    with RuntimeContext(token_id=request.token_id):
        await graph.ainvoke(...)   # 签名里没有 token_id

# 深处
def query_blood_pressure(...):
    token_id = get_token_id()      # 从「当前上下文」读
```

**调用关系是动态的**：`chat` 并没有直接 `import` 并调用 `query_blood_pressure`，而是 Graph → Agent → LLM 决定调哪个 Tool。  
这种「跳过很多层的横切信息」（用户 ID、trace ID）适合放在 **上下文**，而不是塞进每一层参数。

**若你感到「看不懂 with 里 await 和深处 Tool 怎么连起来」**，往往是卡在这里：  
你习惯顺着**直接调用栈**读代码，而 Agent 系统是 **事件/回调/框架调度**，调用栈在运行时才展开。

---

## 五、缺的基础知识 ②：`contextvars` 是什么

### 5.1 为什么不用全局变量

```python
CURRENT_TOKEN_ID = None  # 全局

def handle_request_a():
    CURRENT_TOKEN_ID = "user_a"
    ...

def handle_request_b():
    CURRENT_TOKEN_ID = "user_b"  # 并发时互相覆盖
```

### 5.2 为什么不用 `threading.local`

- 线程本地存储：**一个 OS 线程** 一份
- asyncio 里：**很多协程共用一个线程**，仍会串

### 5.3 `contextvars.ContextVar`（Python 3.7+）

- 每个 **逻辑上下文**（可理解为 Task / 协程链）有自己的一份值
- `set(value)` 只影响**当前上下文**及之后继承它的子 Task
- `get()` 读当前上下文的值
- `reset(token)` 恢复到 `set` 之前

本项目定义了三个变量：

```python
_token_id_context: contextvars.ContextVar[Optional[str]] = ...
_session_id_context: ...
_trace_id_context: ...
```

Tool 里：

```python
token_id = get_token_id()  # 等价于 _token_id_context.get()
```

**你要建立的心智模型：**

> 不是「有一个全局字典存 token_id」，而是「**当前这次请求的执行流**上挂了一个 token_id，谁在这条流里运行都能 `get` 到」。

---

## 六、缺的基础知识 ③：`await` 在 `with` 里，上下文会丢吗？

### 6.1 常见误解

> 「`with` 块里一 `await`，控制权让出去了，ContextVar 是不是就清空了？」

**不会。** `contextvars` 的设计目标之一就是：**在 async/await 链路上保持上下文**。

时间线：

```
with RuntimeContext(...):     # set token_id = "U123"
    await graph.ainvoke(...)   # 暂停、恢复，仍在同一 Task 上下文
        → Agent 节点
        → await llm.ainvoke(...)
        → Tool: get_token_id()  → 仍是 "U123"
# __exit__ reset
```

只要 Tool 的执行还在**同一条 asyncio Task 上下文链**上（LangGraph/LangChain 默认如此），`get_token_id()` 就能读到。

### 6.2 什么时候会丢？

- 在 **`with` 外** 调 Tool → 读不到（chat 里解析 `flow_msgs` 在 `with` 外，那里不需要 token_id，是故意的）
- 手动 `asyncio.create_task(...)` 且未正确继承上下文（少数坑；一般框架会处理）
- 从未 `with` / `set` 就调 Tool → 得到 `None`

---

## 七、缺的基础知识 ④：和 LangGraph `state` 的分工

| 机制 | 存什么 | 谁读写 | 典型字段 |
|------|--------|--------|----------|
| **`FlowState` / `initial_state`** | 业务流程状态 | Graph 节点显式读写 | `history_messages`、`prompt_vars`、`edges_var` |
| **`RuntimeContext` / ContextVar** | 请求级元数据 | Tool、日志等任意深处 `get_*()` | `token_id`、`session_id`、`trace_id` |

`initial_state` 里其实也有 `token_id` 字段，但 **LangChain Tool 不会自动从 state 取 token_id 注入工具**。  
所以业务 Tool 用 `get_token_id()`；state 里的同名字段更多给节点逻辑或持久化用。

理解这层分工后，就不会问「state 里已经有了，为什么还要 ContextVar？」——**传递路径不同**。

---

## 八、对照 chat.py：为什么 `with` 只包 `ainvoke`

```python
with RuntimeContext(...):
    config = {...}
    result = await graph.ainvoke(initial_state, config)

# with 外：从 result 解析 AI 回复
flow_msgs = result.get("flow_msgs", [])
```

| 代码段 | 是否需要 token_id | 是否在 with 内 |
|--------|-------------------|----------------|
| `graph.ainvoke` 及内部 Tool | **需要** | ✅ |
| 解析 `flow_msgs` 返回 HTTP | 不需要 | ❌ |

这是 **最小作用域**：只在「可能触发 Tool」的执行段注入上下文，避免后续代码误依赖隐式全局。

---

## 九、嵌套 `with` 在本项目里是什么角色？

`RuntimeContext` **支持**嵌套（内层 `__exit__` 只恢复内层，`__enter__` 保存了外层 token）：

```python
with RuntimeContext(token_id="outer"):
    with RuntimeContext(token_id="inner"):
        get_token_id()  # "inner"
    get_token_id()      # "outer"
get_token_id()          # 进入最外层之前的值
```

但当前业务代码 **几乎没有内层再包一层 RuntimeContext**。  
因此嵌套不是你现在必须理解的前提；**单层 with 的 set/reset 才是核心。**

---

## 十、学习路径建议（按顺序补基础）

若从零开始，建议按下面顺序阅读/实践：

| 顺序 | 主题 | 要搞懂的一句话 |
|------|------|----------------|
| 0 | **本文「零、从零开始」** | `with` = 自动配对「准备资源」和「清理资源」 |
| 1 | 动手写 3 个 `with open` 小脚本 | 读文件、写文件、块内故意报错，确认仍会 close |
| 2 | Python 上下文管理器 | `with` = 固定配对 `__enter__` / `__exit__` |
| 3 | `contextvars` 官方文档 | 协程安全的「当前上下文变量」，不是全局变量 |
| 4 | asyncio 与 Context 传播 | `await` 不会自动清 ContextVar；Task 继承父上下文 |
| 5 | 横切关注点 | 日志、用户身份、trace 适合隐式传递，不适合每层加参数 |
| 6 | LangChain Tool 调用模型 | Tool 参数来自 LLM JSON，不是 Python 调用栈上的局部变量 |
| 7 | 读本仓库 3 个文件 | `context.py` → `chat.py` 的 with 块 → `blood_pressure_tool.py` 的 `get_token_id()` |

**推荐动手的实验（由易到难）：**

0. 新建 `test.txt`，用 `with open` 读一次、写一次，观察不需要写 `close()`。
1. 临时去掉 `with`，只留 `set_token_id`，故意让 `ainvoke` 抛异常，观察 reset 的价值。
2. 在 `blood_pressure_tool` 里打日志 `get_token_id()`，对比在 `with` 内调 Tool 与在 `with` 外手动调 Tool 的差异。

---

## 十一、FAQ 速查

**Q：`with` 和 `with open` 是什么关系？**  
A：`with` 是语法关键字；`open` 是打开文件的函数。`with open(...) as f:` 表示「打开文件，用完后自动 close」。详见本文「零」。

**Q：`with` 和直接调用 `set_token_id()` 有什么区别？**  
A：`with` = 自动 `set` + 保证 `reset`；单独 `set` 容易忘记恢复。

**Q：没有嵌套 with，能否改成装饰器 `@inject_context`？**  
A：可以，本质仍是 enter/exit；`with` 是最显式的写法，作用域一眼可见。

**Q：测试里 Tool 读不到 token_id？**  
A：测试也要 `with RuntimeContext(token_id="test_user"):` 包一层，或 mock `get_token_id`。

**Q：和 Langfuse 的 trace 重复吗？**  
A：不重复。Langfuse 管 **LLM 观测**；RuntimeContext 管 **业务 Tool 拿 user_id**。可共用同一个 `trace_id` 字符串做关联。

---

## 十二、一句话总结

> **`with` 的本质：** 进入代码块时「准备好某样东西」，离开时「无论成功还是失败都自动收拾干净」。`with open` 收拾的是文件；`with RuntimeContext` 收拾的是请求上下文。  
> **RuntimeContext 不是为了嵌套**，而是为了在 graph 执行期间写入 user/session/trace，并在结束时可靠地擦掉。

---

## 十三、相关代码索引

| 文件 | 说明 |
|------|------|
| `backend/domain/tools/context.py` | `ContextVar` 与 `RuntimeContext` 实现 |
| `backend/app/api/routes/chat.py` | 生产入口，`with` 包裹 `graph.ainvoke` |
| `backend/domain/tools/blood_pressure_tool.py` | `get_token_id()` 消费方 |
| `ai_docs/26061601-RuntimeContext面试介绍.md` | 面试向 1～3 分钟版介绍 |
