# API 文档

本目录包含项目的 API 接口文档，采用 OpenAPI 3.0.3 标准格式编写。

## 文档文件

- `chat-api-openapi.yaml` - 聊天接口的 OpenAPI 规范文档

## 如何使用

### 1. 在线查看

#### 使用 Swagger Editor
1. 访问 [Swagger Editor](https://editor.swagger.io/)
2. 将 `chat-api-openapi.yaml` 文件内容复制粘贴到编辑器中
3. 即可查看和测试 API 文档

#### 使用 ReDoc
1. 访问 [ReDoc](https://redocly.github.io/redoc/)
2. 在页面中输入 OpenAPI 文档的 URL 或直接粘贴 YAML 内容
3. 即可查看格式化的 API 文档

### 2. 集成到 FastAPI 应用

FastAPI 自动支持 OpenAPI 规范。启动应用后，可以通过以下方式访问：

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

### 3. 代码生成

可以使用 OpenAPI 文档生成客户端代码：

#### 使用 openapi-generator
```bash
# 安装 openapi-generator
npm install @openapitools/openapi-generator-cli -g

# 生成 Python 客户端
openapi-generator-cli generate \
  -i chat-api-openapi.yaml \
  -g python \
  -o ./generated-client
```

#### 使用 swagger-codegen
```bash
# 生成 Python 客户端
swagger-codegen generate \
  -i chat-api-openapi.yaml \
  -l python \
  -o ./generated-client
```

### 4. API 测试

#### 使用 curl
```bash
curl -X POST "http://localhost:8000/api/v1/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "我想记录血压，收缩压120，舒张压80",
    "session_id": "session_123456",
    "user_id": "user_789"
  }'
```

#### 使用 httpie
```bash
http POST http://localhost:8000/api/v1/chat \
  message="我想记录血压，收缩压120，舒张压80" \
  session_id="session_123456" \
  user_id="user_789"
```

#### 使用 Postman
1. 导入 `chat-api-openapi.yaml` 文件到 Postman
2. Postman 会自动识别 API 结构并生成请求集合
3. 可以直接在 Postman 中测试接口

## 接口说明

### POST /api/v1/chat

聊天对话接口，处理用户消息并返回智能体回复。

**请求参数：**
- `message` (string, 必填): 用户消息内容
- `session_id` (string, 必填): 会话ID，用于标识同一会话
- `user_id` (string, 必填): 用户ID
- `conversation_history` (array, 可选): 对话历史

**响应字段：**
- `response` (string): 助手回复内容
- `session_id` (string): 会话ID
- `intent` (string, 可选): 识别的意图
- `agent` (string, 可选): 使用的智能体名称

**状态码：**
- `200`: 成功
- `400`: 请求参数错误
- `500`: 服务器内部错误

详细说明请参考 `chat-api-openapi.yaml` 文件。

## 更新文档

当 API 接口发生变化时，需要同步更新 OpenAPI 文档：

1. 修改 `chat-api-openapi.yaml` 文件
2. 确保文档与实际代码保持一致
3. 更新本文档中的示例（如需要）

## 参考资源

- [OpenAPI 规范](https://swagger.io/specification/)
- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [Swagger Editor](https://editor.swagger.io/)
