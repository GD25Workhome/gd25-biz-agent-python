# 我的总结（草稿）
- 我该做的事情是，尝试将原属案例输入到这个格式的池子中
## 下面为我最终的格式架构
- metaData字段的格式约定（部分来自于我的trace）
    - 标准化查询（trace）
        - user_id
        - session_id
        - token_id
        - flow_key
        - tags
    - 标记信息（数据清洗）
        - AI标记-tags
        - 人工标记-tags
        - 去重-tags
    - 内容的信息（数据清洗）
        - 用户信息
        - 医生信息
    - 流程的信息（trace）
        - 流程key
        - 流程name
        - 流程版本
- input中的必填字段应该是当前消息和历史消息
    - 当前会话（必填）
    - 历史回话
    - 当前会话上下文对象-可以用来造数据
- output的必填字段应该是回复的内容文本
    - 返回给用户的消息（必填）
    - 过程消息
- 问题改写说明
## 格式说明

### DataSet Input

Langfuse DataSet 的 input 数据格式，用于对话数据归档与评估。

- **current_msg** `string`（必填）— 当前会话消息内容，对应 FlowState 中的 `current_message.content`
- **history_messages** `array` — 历史消息列表，对应 FlowState 中的 `history_messages`，元素为 BaseMessage 格式
  - BaseMessage 结构：
    - **type** `string`（必填）— 消息类型标识。常见值：human、ai、system、generic、chat
    - **content** `string | array`（必填）— 消息内容，可为字符串或复杂内容列表
    - additional_kwargs `object` — 附加数据，如 tool_calls 等
    - name `string` — 消息的可读名称
    - id `string` — 消息唯一标识
    - response_metadata `object` — 响应元数据，如 token 计数、模型名等
- **context** `object` — 当前会话上下文对象，可用于造数据，不限制具体格式

### DataSet Output

Langfuse DataSet 的 output 数据格式，用于对话数据归档与评估。

- **response_message** `string`（必填）— 返回给用户的消息，流程最终回复的文本内容
- **flow_msgs** `array` — 过程消息列表，对应 FlowState 中的 `flow_msgs`，元素为 BaseMessage 格式
  - BaseMessage 结构：（同上 Input 中 BaseMessage）
- **other_meta_data** `object` — 其它冗余信息，不限制具体格式

### DataSet Metadata

Langfuse DataSet Item 的 metadata 格式，query_ 前缀扁平 key + content_info 层级（020308）。

- **query_message_id** `string` — 消息 ID（标准化查询）
- **query_session_id** `string` — 会话 ID（标准化查询）
- **query_user_id** `string` — 用户 ID（标准化查询）
- **query_flow_key** `string` — 流程 key（标准化查询）
- **query_tags** `array` — 标签列表（标准化查询）
- **content_info** `object` — 内容的信息（langfuse dataSetItems 作为case调用时用）
  - user_info `object` — 用户信息（原 input.context：age、disease、blood_pressure、symptom 等）
  - patient_info `object` — 患者信息，可扩展属性
    - patient_id `string` — 患者 ID
  - doctor_info `object` — 医生信息，可扩展属性
    - doctor_id `string` — 医生 ID
  - ext `string` — 扩展信息（原 other_meta_data.ext）
- **data_cleaning_tags** `object` — 标记信息（数据清洗过程中使用）
  - ai_tags `array` — AI 标记
  - human_tags `array` — 人工标记
  - dedup_tags `array` — 去重标记
- **flow_info** `object` — 流程的信息（一般来源于trace）
  - flow_key `string` — 流程 key
  - flow_name `string` — 流程 name
  - flow_version `string` — 流程版本
