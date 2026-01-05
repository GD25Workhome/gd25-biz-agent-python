# Langfuse未记录问题排查指南

## 问题描述

请求模型后，模型正常回复，但在Langfuse中看不到记录。

## 排查步骤

### 1. 检查配置（从统一配置模块读取）

**重要**：所有配置统一通过 `backend/app/config.py` 模块管理，从 `.env` 文件读取。

首先确认 `.env` 文件中的配置是否正确设置：

```env
# 必须设置为 true
LANGFUSE_ENABLED=true

# 必须设置（从Langfuse控制台获取）
LANGFUSE_PUBLIC_KEY=your_public_key
LANGFUSE_SECRET_KEY=your_secret_key

# 可选，如果使用自托管Langfuse
LANGFUSE_HOST=http://10.160.4.84:3000
```

**检查方法**：
```bash
# 在项目根目录执行（从统一配置模块读取）
python -c "from backend.app.config import settings; print('LANGFUSE_ENABLED:', settings.LANGFUSE_ENABLED); print('LANGFUSE_PUBLIC_KEY:', 'SET' if settings.LANGFUSE_PUBLIC_KEY else 'NOT SET'); print('LANGFUSE_SECRET_KEY:', 'SET' if settings.LANGFUSE_SECRET_KEY else 'NOT SET'); print('LANGFUSE_HOST:', settings.LANGFUSE_HOST or 'NOT SET')"
```

**配置位置**：
- 配置文件：`backend/app/config.py`
- 配置来源：项目根目录的 `.env` 文件
- 使用方式：`from backend.app.config import settings`

### 2. 运行诊断工具

运行诊断工具检查Langfuse配置和连接状态：

```bash
# 方法1：使用pytest
pytest cursor_test/test_langfuse_diagnosis.py::test_full_diagnosis -v -s

# 方法2：直接运行Python脚本
python cursor_test/test_langfuse_diagnosis.py
```

诊断工具会检查：
- ✅ 环境变量配置
- ✅ Langfuse客户端创建
- ✅ Trace创建
- ✅ CallbackHandler创建

### 3. 检查日志输出

查看应用日志，查找以下关键日志：

**成功日志**：
```
[Langfuse] Langfuse客户端初始化成功: host=http://10.160.4.84:3000, public_key_prefix=xxx...
[Langfuse] 创建Trace成功: name=chat_request, trace_id=xxx, user_id=xxx, session_id=xxx
[Langfuse] CallbackHandler创建成功: host=http://10.160.4.84:3000, context={...}
[Langfuse] 自动添加CallbackHandler: provider=xxx, model=xxx, callbacks_count=1
```

**失败日志**：
```
Langfuse未启用（LANGFUSE_ENABLED=false）
Langfuse配置不完整：缺少LANGFUSE_PUBLIC_KEY或LANGFUSE_SECRET_KEY
Langfuse客户端初始化失败: ...
创建Langfuse Trace失败: ...
CallbackHandler创建失败: ...
```

### 4. 常见问题及解决方案

#### 问题1：配置未设置

**症状**：日志显示"Langfuse未启用"或"配置不完整"

**解决方案**：
1. 确认项目根目录的`.env`文件中包含所有必需的配置：
   ```env
   LANGFUSE_ENABLED=true
   LANGFUSE_PUBLIC_KEY=your_key
   LANGFUSE_SECRET_KEY=your_secret
   LANGFUSE_HOST=http://10.160.4.84:3000
   ```
2. 确认`.env`文件在项目根目录（与`backend`目录同级）
3. 重启应用使配置生效

#### 问题2：Langfuse客户端初始化失败

**症状**：日志显示"Langfuse客户端初始化失败"

**可能原因**：
- 网络连接问题（无法访问Langfuse服务器）
- 认证失败（PUBLIC_KEY或SECRET_KEY错误）
- Langfuse服务器未启动

**解决方案**：
1. 检查网络连接：
   ```bash
   curl http://10.160.4.84:3000/health
   ```
2. 验证密钥是否正确
3. 检查Langfuse服务器是否正常运行

#### 问题3：Trace创建但LLM调用未记录

**症状**：Trace创建成功，但看不到LLM调用记录

**可能原因**：
- CallbackHandler未正确添加到LLM客户端
- CallbackHandler未关联到Trace

**解决方案**：
1. 检查日志中是否有"自动添加CallbackHandler"的日志
2. 确认`get_llm`函数被调用时，CallbackHandler被添加
3. 检查Langfuse版本兼容性

#### 问题4：host参数问题

**症状**：使用自托管Langfuse时，host参数可能为None

**解决方案**：
- 确保`LANGFUSE_HOST`环境变量已设置
- 代码已修复，如果host为None会使用默认值，但建议明确设置

### 5. 代码修复说明

已修复的问题：

1. **host参数处理**：
   - 如果`LANGFUSE_HOST`未设置，Langfuse会使用默认值
   - 添加了警告日志提示host未设置

2. **诊断日志增强**：
   - 所有Langfuse相关操作都添加了`[Langfuse]`前缀
   - 增加了更详细的错误日志

3. **CallbackHandler创建**：
   - 添加了配置检查
   - 增加了详细的日志输出

### 6. 验证步骤

1. **设置环境变量**：
   ```bash
   export LANGFUSE_ENABLED=true
   export LANGFUSE_PUBLIC_KEY=your_public_key
   export LANGFUSE_SECRET_KEY=your_secret_key
   export LANGFUSE_HOST=http://10.160.4.84:3000
   ```

2. **运行诊断工具**：
   ```bash
   python cursor_test/test_langfuse_diagnosis.py
   ```

3. **发送测试请求**：
   - 发送一个聊天请求
   - 查看日志输出
   - 检查Langfuse控制台

4. **检查日志**：
   - 查找`[Langfuse]`开头的日志
   - 确认Trace和CallbackHandler都创建成功

### 7. 如果仍然无法记录

如果按照以上步骤仍然无法记录，请：

1. **收集日志**：
   - 启动应用时的日志
   - 请求处理时的日志
   - 查找所有`[Langfuse]`相关的日志

2. **检查Langfuse版本**：
   ```bash
   pip show langfuse
   ```
   确保版本 >= 2.0.0

3. **手动测试Langfuse连接**：
   ```python
   from langfuse import Langfuse
   client = Langfuse(
       public_key="your_key",
       secret_key="your_secret",
       host="http://10.160.4.84:3000"
   )
   trace = client.trace(name="test")
   print(f"Trace ID: {trace.id}")
   ```

4. **联系支持**：
   - 提供完整的日志
   - 提供环境变量配置（隐藏密钥）
   - 提供Langfuse版本信息

