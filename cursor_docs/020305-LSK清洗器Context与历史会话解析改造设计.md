# LSK 清洗器 Context 与历史会话解析改造设计

## 1. 背景与问题

### 1.1 当前 LSK 清洗器现状

`LskCleaner`（`parsers/cleaners/lsk.py`）用于处理 `4.1 lsk_副本.xlsx`，当前实现：

- **列映射**：仅抓取 `新会话`、`新会话响应`、`ids`
- **输出**：`current_msg`、`response_message`、`message_id`，`history_messages` 恒为空，`context` 未填充

### 1.2 缺失功能

| 功能 | 说明 |
|------|------|
| **Context 抓取** | 未抓取 `年龄`、`疾病`、`血压`、`症状`、`用药`、`用药情况`、`习惯`、`历史Action`、`ext`，未写入 `input.context` |
| **历史会话解析** | `历史会话`、`历史会话响应` 两列存在但未解析为 `history_messages`，或解析逻辑不符合实际数据格式 |

### 1.3 实际数据格式

**历史会话** 示例：

```
第1轮提问-----------
messageId: c3f30444-25a0-4886-a058-86d7a1447d3f
我刚才做完检查后又挂了心血管内科的医生，说发泡实验阳性3级，建议做手术把小洞补上，想知道我的手麻木症状时这个问题导致的吗
第2轮提问-----------
messageId: 24f7a96b-9a5f-4922-b4cc-3bc6e058d0a5
早上好，今天早上测了127/75/89，我先观察一下吧！谢谢你
==================
```

**历史会话响应** 示例：

```
第1轮响应
content=发泡实验阳性3级提示心脏可能存在卵圆孔未闭（PFO），这种心脏结构异常确实可能与一些神经系统症状有关联。手麻木症状是否由这个问题引起...
第2轮响应
content=你能主动监测并告诉我血压情况，这个习惯非常棒！这次的血压127/75mmHg已经达到了你135/85mmHg的目标值...
>>>>>>>>>>>>>>>>>>>>>>
```

**清洗规则**：

- **历史会话**：剔除 `第N轮提问-----------`、`messageId: xxx` 所在行，保留实际提问内容
- **历史会话响应**：剔除 `第N轮响应` 所在行，提取 `content=` 后的内容

---

## 2. 设计目标

1. 将 `年龄`、`疾病`、`血压`、`症状`、`用药`、`用药情况`、`习惯`、`历史Action` 写入 `input.context`
2. 将 `ext` 写入 `expected_output.other_meta_data.ext`
3. 正确解析 `历史会话` + `历史会话响应` 为 `history_messages`：`[human1, ai1, human2, ai2, ...]`

---

## 3. 详细设计

### 3.1 Context 抓取

参考 `Sh1128Cleaner` 的 `_extract_context` 与 `_CONTEXT_COL_MAP`，为 LSK 增加：

| context key | Excel 列名 |
|-------------|------------|
| age | 年龄 |
| disease | 疾病 |
| blood_pressure | 血压 |
| symptom | 症状 |
| medication | 用药 |
| medication_status | 用药情况 |
| habit | 习惯 |
| history_action | 历史Action |

实现方式：在 `LskCleaner` 中增加 `_CONTEXT_COL_MAP` 与 `_extract_context()`，类型与长度约束与 Sh1128 一致（如 `age` 用 `convert_to_int`，其余用 `convert_to_string`/`convert_to_text`）。

### 3.2 历史会话解析逻辑

LSK 的 `历史会话` / `历史会话响应` 与 Sh1128 的 Q/A 格式不同，需单独解析函数。

#### 3.2.1 历史会话（human 消息）

**结构**：`第N轮提问-----------` + 可选 `messageId: xxx` + 实际提问内容，多轮重复。

**解析步骤**：

1. 按 `第\d+轮提问[-=]*` 分割，得到多个块
2. 对每个块：
   - 去掉首行（`第N轮提问...`）
   - 去掉 `messageId: xxx` 或 `message_id: xxx` 行（整行匹配）
   - 剩余内容 strip 后作为 human 消息 content

**正则示例**：

```python
# 分割：第1轮提问-----------、第2轮提问======== 等
re.split(r"第\d+轮提问[-=]*\s*", text)
```

#### 3.2.2 历史会话响应（ai 消息）

**结构**：`第N轮响应` + `content=...`（可能多行），多轮重复。

**解析步骤**：

1. 按 `第\d+轮响应` 分割，得到多个块
2. 对每个块：
   - 查找 `content=` 或 `content：`，提取其后内容直到下一个 `第N轮响应` 或结尾
   - 若块内无 `content=`，可尝试整块作为 content（兼容）

**正则示例**：

```python
# 提取 content= 后的值，支持 content= 或 content：
re.search(r"content\s*[=：]\s*([\s\S]*?)(?=第\d+轮响应|\Z)", block)
```

#### 3.2.3 交替合并

将 human 列表与 ai 列表按轮次交替合并为 `[human1, ai1, human2, ai2, ...]`。若轮数不一致，以较短者为准，多余轮次丢弃。

---

### 3.3 代码结构

#### 3.3.1 新增解析函数（建议放在 `parsers/base.py` 或 `parsers/cleaners/lsk.py`）

| 函数 | 职责 |
|------|------|
| `parse_lsk_history_session(text)` | 历史会话 → `List[str]`（human 内容列表） |
| `parse_lsk_history_response(text)` | 历史会话响应 → `List[str]`（ai 内容列表） |
| `merge_history_to_messages(humans, ais)` | 合并为 `[{"type":"human","content":...},{"type":"ai","content":...}, ...]` |

**放置建议**：LSK 专用格式与 Sh1128 的 Q/A 格式不同，建议将 `parse_lsk_history_*` 放在 `lsk.py` 内，避免 base 膨胀；`merge_history_to_messages` 若可复用可放 base。

#### 3.3.2 LskCleaner 改造

```python
# 伪代码
def clean(self, row, df):
    current = ...
    response = ...
    msg_id = ...
    context = self._extract_context(row, df)  # 新增
    ext = convert_to_text(row.get("ext")) if "ext" in df.columns else None  # 新增

    history_session = convert_to_text(row.get("历史会话")) if "历史会话" in df.columns else None
    history_response = convert_to_text(row.get("历史会话响应")) if "历史会话响应" in df.columns else None
    history_messages = self._parse_history_messages(history_session, history_response)  # 新增

    return [CanonicalItem(
        current_msg=current,
        history_messages=history_messages,
        response_message=response,
        message_id=msg_id,
        context=context,
        ext=ext,
    )]
```

---

## 4. 实现任务清单

| 序号 | 任务 | 文件 |
|------|------|------|
| 1 | 在 `LskCleaner` 中增加 `_CONTEXT_COL_MAP`（含历史Action）、`_extract_context()` | `parsers/cleaners/lsk.py` |
| 2 | 实现 `parse_lsk_history_session()`：按 `第N轮提问` 分割，剔除 messageId 行，提取提问内容 | `parsers/cleaners/lsk.py` |
| 3 | 实现 `parse_lsk_history_response()`：按 `第N轮响应` 分割，提取 `content=` 值 | `parsers/cleaners/lsk.py` |
| 4 | 实现 `_parse_history_messages()`：调用上述函数并合并为 `[human,ai,human,ai,...]` | `parsers/cleaners/lsk.py` |
| 5 | 在 `clean()` 中提取 `历史会话`、`历史会话响应`、`ext`，填充 `context`、`history_messages`、`ext` | `parsers/cleaners/lsk.py` |
| 6 | 编写单元测试：context 抓取、历史会话解析、空值/缺列兼容 | `cursor_test/test_feishu_import_lsk.py` |

---

## 5. 边界与兼容

- **缺列**：若 `历史会话`、`历史会话响应` 不存在，`history_messages` 为空列表
- **空值**：`convert_to_text` 已处理 `-`、空字符串等，无需额外逻辑
- **轮数不一致**：human 与 ai 数量不同时，按较短列表长度截断
- **无法解析**：若正则无法匹配，可退化为整段作为单条 human 或 ai（与 Sh1128HistoryQACleaner 类似）

---

## 6. 与现有架构关系

- **CanonicalItem**：已支持 `context`、`ext`、`history_messages`，无需改动
- **canonical_to_dataset_item**：已正确写入 `input.context`、`expected_output.other_meta_data.ext`，无需改动
- **Sh1128 系列**：LSK 解析逻辑独立，不影响 Sh1128Cleaner / Sh1128HistoryQACleaner

---

## 7. 完成情况

| 序号 | 任务 | 状态 | 说明 |
|------|------|------|------|
| 1 | 在 LskCleaner 中增加 _CONTEXT_COL_MAP（含历史Action）、_extract_context() | ✅ 已完成 | `parsers/cleaners/lsk.py` |
| 2 | 实现 parse_lsk_history_session() | ✅ 已完成 | 按 第N轮提问 分割，剔除 messageId 行 |
| 3 | 实现 parse_lsk_history_response() | ✅ 已完成 | 按 第N轮响应 分割，提取 content= 值 |
| 4 | 实现 _parse_history_messages()、merge_history_to_messages() | ✅ 已完成 | 交替合并为 [human,ai,...] |
| 5 | 在 clean() 中提取历史会话、历史会话响应、ext，填充 context、history_messages、ext | ✅ 已完成 | `parsers/cleaners/lsk.py` |
| 6 | 编写单元测试 | ✅ 已完成 | `cursor_test/test_feishu_import_lsk.py`，15 个用例全部通过 |

**测试命令**：`pytest cursor_test/test_feishu_import_lsk.py cursor_test/test_feishu_import_multi_qa.py -v`
