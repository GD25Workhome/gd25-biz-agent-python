# M6 测试：LangChain reasoning_content 提取可行性验证

## 测试目标

本测试目录包含用于验证 LangChain 是否能够提取 `reasoning_content` 字段的测试代码。

## 测试文件

### `test_reasoning_content_extraction.py`

非 pytest 测试脚本，直接运行即可。

**测试内容**：

1. **测试1：验证原始行为**
   - 验证 LangChain 的 `_convert_dict_to_message` 函数确实会丢弃 `reasoning_content` 字段
   - 验证 `additional_kwargs` 中不包含 `reasoning_content`

2. **测试2：验证 Monkey Patch 方案**
   - 验证通过 Monkey Patch 可以成功保留 `reasoning_content` 字段
   - 验证 `additional_kwargs` 中可以包含 `reasoning_content`

3. **测试3：验证 additional_kwargs 机制**
   - 验证 `AIMessage` 对象支持 `additional_kwargs` 字段
   - 验证可以手动设置和读取 `reasoning_content`

4. **测试4：字段保留对比**
   - 对比哪些字段会被保留（如 `function_call`, `tool_calls`, `audio`）
   - 对比哪些字段会被丢弃（如 `reasoning_content`, `custom_field`）

## 运行方式

```bash
# 进入项目根目录
cd /Users/m684620/work/github_GD25/gd25-biz-agent-python_cursor

# 运行测试（需要激活正确的 conda 环境）
python cursor_test/M6_test/test_reasoning_content_extraction.py
```

## 预期结果

- ✅ 测试1 应该通过：原始函数确实丢弃了 `reasoning_content`
- ✅ 测试2 应该通过：Monkey Patch 成功保留了 `reasoning_content`
- ✅ 测试3 应该通过：`additional_kwargs` 机制正常工作
- ✅ 测试4 应该通过：能够正确识别哪些字段被保留/丢弃

## 测试原理

### 问题根源

LangChain 的 `_convert_dict_to_message` 函数在转换消息字典时，**硬编码**了需要保留的字段列表：

```python
additional_kwargs: Dict = {}
if function_call := _dict.get("function_call"):
    additional_kwargs["function_call"] = dict(function_call)
# ... tool_calls, audio 等
```

由于 `reasoning_content` 不在这个列表中，因此被丢弃。

### 解决方案

通过 Monkey Patch 替换 `_convert_dict_to_message` 函数，在保留原有逻辑的基础上，额外保留 `reasoning_content` 字段：

```python
def _enhanced_convert_dict_to_message(_dict):
    message = _original_convert(_dict)
    if isinstance(message, AIMessage) and 'reasoning_content' in _dict:
        message.additional_kwargs['reasoning_content'] = _dict['reasoning_content']
    return message
```

## 相关文档

- [002-LangChain思考过程提取可行性深度分析.md](../../doc/设计V6.0/思考过程的记录/002-LangChain思考过程提取可行性深度分析.md)
- [001-思考过程调用方案.md](../../doc/设计V6.0/思考过程的记录/001-思考过程调用方案.md)

