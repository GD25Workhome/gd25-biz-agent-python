# Rewritten 流程：LLM 返回 JSON 格式差异与解析失败原因

## 一、你观察到的两种格式

| 类型 | 示例 | `content` 类型 | 当前代码下解析结果 |
|------|------|----------------|--------------------|
| **解析成功时的格式** | Untitled-3 | **对象 (dict)**：`"content": { "场景描述": "...", "患者提问": "...", ... }` | 见下文 → 实际会失败 |
| **解析失败时的格式** | Untitled-2、Untitled-1 | **字符串 (str)**：`"content": "{\n  \"场景描述\": \"...\", ... }"` | 见下文 → 可能失败 |

提示词要求的是「严格 JSON、不可包含任何其他内容」，但**模型/接口可能返回两种形态**：

1. **结构化**：`content` 已是解析好的对象（如豆包等部分接口直接返回 dict）。
2. **字符串**：`content` 是 JSON 字符串，且字段值里可能包含 `{`、`}`（如「回复案例」长文本）。

当前代码只按「字符串 + 简单截取」处理，且不处理 dict，因此两种格式都会出问题。

---

## 二、当前代码为何导致「有时成功、有时失败」

### 2.1 数据流

- **factory.py**：从最后一条 AI 消息取 `msg.content`，得到 `output`，再 `return {"output": output, "messages": ...}`。
- **agent_creator.py**：只认 `result["output"]`，且**仅当 `isinstance(output, str)` 时**才做 JSON 解析并写入 `edges_var`。

### 2.2 格式一：`content` 为 **dict**（Untitled-3，你标为「解析成功」）

- factory 中：`output = msg.content if isinstance(msg.content, str) else str(msg.content)`  
  → 得到 `output = str(dict)`，即 Python 的 repr，例如 `"{'场景描述': '...', ...}"`（单引号、可能带 `u'` 等）。
- agent_creator 中：`isinstance(output, str)` 为 True，会进入解析分支；但 `json.loads(json_str)` 要求**双引号**，对单引号的 repr **会报错**，被 `except` 吞掉，**edges_var 保持空**。

若你这边的「解析成功」是指：**当接口返回的就是 dict 时，你希望流程能成功**，那当前代码恰恰**没有**对 dict 做分支，反而把 dict 转成非法“JSON”字符串，导致失败。

### 2.3 格式二：`content` 为 **字符串**（Untitled-2/1，你标为「解析失败」）

- 此时 `output` 就是整段 JSON 字符串。
- agent_creator 用 `json_start = output.find("{")` 和 `json_end = output.rfind("}") + 1` 截取子串再 `json.loads`。
- **问题**：JSON 里「回复案例」「回复规则」等字段的值是长文本，中间可能包含字面量 `}` 或 `{`。  
  `rfind("}")` 会定位到**整个字符串中最后一个 `}`**，若这个 `}` 出现在某个**字段值内部**（而不是根对象的结束括号），截取的 `output[json_start:json_end]` 就不是合法 JSON，`json.loads` 会报错，同样被 except 吞掉，**edges_var 为空**。

因此：**两种格式在当前实现下都可能解析失败**——dict 被错误地转成字符串；字符串又可能被 `rfind("}")` 截错。

---

## 三、建议的代码改动方向（与提示词无关）

提示词（严格 JSON、不可包含其他内容）可以保持不变；问题在于**下游要同时支持两种返回形态，并对字符串做更稳健的解析**。

1. **支持 `content` 为 dict**
   - 在 **factory**：若 `msg.content` 已是 `dict`，除 `output`（可继续用 `str(content)` 用于日志/flow_msgs）外，可额外把原始 dict 传给 agent（例如 `output_data=msg.content`），或在 agent_creator 侧从 `result` 里取到 dict。
   - 在 **agent_creator**：若 `result["output"]` 或专门字段是 **dict**，直接把它当作「解析好的业务 JSON」，按现有规则（跳过 `response_content` 等）写入 `edges_var`，**不再**做 `str` + `json.loads`。

2. **字符串解析更稳健**
   - 当 `output` 为 str 时：
     - 先尝试 **整段** `json.loads(output)`；成功则直接用。
     - 若失败，再尝试「从第一个 `{` 开始，按括号匹配找到与根 `{` 对应的 `}`」再截取并 `json.loads`，避免用简单的 `rfind("}")` 在值内 `}` 上截断。

3. **日志**
   - 在解析失败时用 `logger.warning` 打出格式（type(content)）、长度或前 200 字符，便于区分是 dict 被误转成 str，还是字符串截取错误。

按上述修改后，「解析成功时的格式」（content=dict）和「解析失败时的格式」（content=长 JSON 字符串）都能被正确解析，edges_var 会稳定有值（在模型确实返回了所需字段的前提下）。

---

## 四、相关代码位置

| 文件 | 说明 |
|------|------|
| `backend/domain/agents/factory.py` 约 72–84 行 | 取 `msg.content`，`str(msg.content)` 导致 dict 变非法“JSON” |
| `backend/domain/flows/nodes/agent_creator.py` 约 108–141 行 | 仅处理 `isinstance(output, str)`，用 `find("{")` / `rfind("}")` 截取后 `json.loads` |
| `config/flows/pipeline_step2/prompts/rewritten_agent.md` 120–137 行 | 要求严格 JSON 输出，与格式差异无关，可保留 |

---

*文档编号：021004；与 021003（edges_var 丢失与并发）、021002（update_rewritten_data 链路）配套。*
