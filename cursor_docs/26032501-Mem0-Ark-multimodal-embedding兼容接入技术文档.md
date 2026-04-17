## Mem0 与 Ark multimodal embedding 兼容接入技术文档

### 背景与问题描述
在 `cursor_test/express_customer_service copy.py` 的 Mem0 集成中，目标 embedding 服务为火山引擎（Ark）multimodal embeddings，期望请求满足以下“真实接口契约”：

1. 请求地址：
   - `https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal`
2. 请求 body schema（示例）：
   ```json
   {
     "model": "doubao-embedding-vision-251215",
     "input": [
       {
         "type": "text",
         "text": "天很蓝，海很深"
       }
     ]
   }
   ```

但当使用 Mem0 内置 `embedder.provider="openai"`（并通过 `openai_base_url` 配置自定义 base URL）时，观察到 Mem0 生成的请求与上述契约存在两个关键差异：

1. endpoint：
   - Mem0 实际只拼接到：`https://ark.cn-beijing.volces.com/api/v3/embeddings`
   - 不能追加 `/multimodal`
2. body schema：
   - Mem0 实际请求 body 类似：
     ```json
     {
       "input": ["你好"],
       "model": "doubao-embedding-vision-250615",
       "dimensions": 1024,
       "encoding_format": "base64"
     }
     ```
   - 与 Ark multimodal embeddings 要求的 `{ "type": "text", "text": ... }` 输入结构不一致

因此，单纯通过 `openai_base_url` 并不能修复 Mem0 openai embedder 的 endpoint 拼接与请求体结构差异。

### 根因分析（基于现有证据）
1. Mem0 的 `openai` embedder 是按 OpenAI Embeddings 语义封装的（其输入通常是 `input: string[]`），并携带 OpenAI 风格的 `dimensions/encoding_format` 等参数。
2. Ark multimodal embeddings 属于其自身的 multimodal 规范，要求 endpoint 使用 `/embeddings/multimodal`，且 input 必须是带 `type/text` 的对象数组。
3. Mem0 当前的 `openai` embedder 配置项（包括 `openai_base_url`）不足以把请求改成 Ark multimodal 所需的 endpoint 与 body schema。

### 可行的解决方案：使用 Mem0 的 `langchain` embedder 扩展点注入自定义 embeddings
Mem0 支持：
`embedder.provider="langchain"`，并允许你直接在 Mem0 配置中传入一个“已初始化的 LangChain embeddings 实例”（其 provider/实现由你控制）。

Mem0 官方文档对 `langchain` embedder 的说明为：通过 `provider="langchain"` 并在 `config.model` 中传入 embeddings 模型实例即可使用（实例内部实现决定如何请求外部 embeddings 服务）。

基于此，推荐方案为：
- 不再使用 Mem0 内置 `openai` embedder
- 改用 Mem0 的 `langchain` embedder，并在 LangChain embeddings 实例内部直接调用 Ark 的 SDK/HTTP，使其天然满足：
  - endpoint：`/embeddings/multimodal`
  - body schema：`input: [{ "type": "text", "text": ... }]`

### 方案设计要点
1. 自定义一个 Ark embeddings wrapper（LangChain embeddings 兼容）
   - 需要实现的方法至少包含：
     - `embed_documents(texts: List[str]) -> List[List[float]]`
     - `embed_query(text: str) -> List[float]`
   - 内部使用你后端/SDK 已验证的方式调用 Ark：
     - `client.multimodal_embeddings.create(model=..., input=[{"type":"text","text": t}])`
     - 解析响应中的 embedding 向量并返回
2. 在 Mem0 配置中替换 embedder provider
   - 把原来的：
     - `EmbedderConfig(provider="openai", ...)`
   - 替换为：
     - `EmbedderConfig(provider="langchain", config={"model": <your_ark_embeddings_instance>})`
3. VectorStore（pgvector）维度一致性
   - 确保你使用的 Ark embedding model 的输出向量维度与 pgvector 的 collection/vector 维度一致。
   - 若系统由 Mem0/pgvector 自动建表，需确认其是否能从你的 embeddings 实例推断 dims；若不能，需手工指定/预建 collection 的维度（具体取决于 Mem0 的建表策略与版本）。

### 建议的实现步骤（落地清单）
1. 在 `cursor_test/express_customer_service copy.py` 中新增/引入一个 Ark embeddings wrapper 类
   - 可直接在文件内实现（用于测试）
   - 或提取到单独模块（用于复用）
2. 修改 Mem0 初始化配置
   - 将 `embedder=EmbedderConfig(provider="openai", ...)` 替换为 `provider="langchain"`，并把 `config.model` 指向你的 Ark embeddings wrapper 实例
3. 验证“契约对齐”
   - 运行一次 `self.mem0.add(...)`
   - 抓包或在日志中确认：
     - 请求 endpoint 是否是 `/embeddings/multimodal`
     - body 是否是 `{"model":..., "input":[{"type":"text","text":...}]}` 结构
4. 验证向量库写入与检索
   - 调用 `self.mem0.search(...)`
   - 确认检索结果与写入一致，不报 dims 相关错误

### 预期收益
- 不依赖 Mem0 openai embedder 对 Ark 的兼容能力
- 通过“注入自定义 LangChain embeddings 实例”，把 endpoint 与请求体契约的控制权完全交还给你
- 可以复用后端已存在的 Ark embedding 代码/解析方式，避免重复造轮子

### 后续建议（可选）
- 将 wrapper 抽到后端/公共模块，避免在测试脚本与服务端重复实现
- 在重跑/批处理 embedding 场景下（如后端的 batch embedding），统一使用同一套 Ark embeddings wrapper，确保请求行为一致性与可观测性（日志/trace）一致

