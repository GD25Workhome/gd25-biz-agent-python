# Function Call 对接 Langfuse 方案

## 一、概述

本文档说明如何将工具调用的执行信息记录到 Langfuse 中，并确保工具执行的 Span 作为 LLM 调用的子节点，形成清晰的层级关系。

**目标**：
1. 在工具执行时创建 Langfuse Span，记录工具执行的详细信息
2. 确保工具执行的 Span 是 LLM 调用 Span 的子节点（自动嵌套）
3. 支持后续扩展二级、三级节点（如数据库操作、外部服务调用等）

**层级结构**：
```
Trace (chat_request)
  └─ Span (agent_{agent_name})              # Agent 节点执行
      └─ Generation (LLM 调用)              # LLM 调用（自动记录）
          └─ Span (tool_{tool_name})        # 工具执行（待实现）⭐
              ├─ Span (db_operation)        # 数据库操作（未来扩展）
              └─ Span (external_api)        # 外部 API 调用（未来扩展）
```

## 二、可行性分析

### 2.1 Langfuse Span 嵌套机制

**Langfuse SDK 支持 Span 嵌套**：
- 使用 `start_as_current_span()` 创建 Span 时，如果当前已有活动的 Span，会自动创建为子 Span
- 使用上下文管理器（`with` 语句）确保 Span 的嵌套关系

**关键 API**：
```python
from langfuse import Langfuse

langfuse_client = Langfuse(...)

# 在父 Span 的上下文中创建子 Span
with langfuse_client.start_as_current_span(
    name="child_span",
    input={},
    metadata={}
):
    # 执行代码
    # 这个 Span 会自动成为当前活动 Span 的子节点
```

### 2.2 当前实现状态

**已实现**：
- ✅ Trace 创建：在 API 入口创建 Trace（`app/api/routes.py`）
- ✅ Agent Span 创建：在 Agent 节点执行时创建 Span（`domain/router/graph.py:211`）
- ✅ LLM Generation 记录：通过 Langfuse Callback Handler 自动记录（`infrastructure/llm/client.py`）
- ✅ 工具包装器：工具执行拦截点已存在（`domain/tools/wrapper.py:ainvoke`）

**待实现**：
- ⏳ 工具执行 Span：在工具执行时创建 Span（`domain/tools/wrapper.py`）

## 三、实现方案

### 3.1 方案设计

**核心思路**：
1. 在工具包装器的 `ainvoke` 方法中，在执行工具前创建 Span
2. 由于工具执行发生在 LLM Generation 的上下文中，创建的 Span 会自动成为 LLM Generation 的子节点
3. 记录工具执行的输入参数、输出结果、执行时间等信息
4. 支持错误记录和异常处理

**实现位置**：
- 主要修改：`domain/tools/wrapper.py` 的 `TokenInjectedTool.ainvoke()` 方法
- 辅助函数：`infrastructure/observability/langfuse_handler.py`（如果需要）

### 3.2 详细实现步骤

#### 步骤 1：在工具包装器中集成 Langfuse Span

**文件位置**：`domain/tools/wrapper.py`

**修改点**：`TokenInjectedTool.ainvoke()` 方法

**实现代码**：

```python
# domain/tools/wrapper.py

import logging
from typing import Any, Dict, Optional
from langchain_core.tools import BaseTool
from langchain_core.callbacks import CallbackManagerForToolRun, AsyncCallbackManagerForToolRun
from langchain_core.messages import ToolMessage

from domain.tools.context import get_token_id
from infrastructure.observability.langfuse_handler import get_langfuse_client
from app.core.config import settings

logger = logging.getLogger(__name__)


class TokenInjectedTool(BaseTool):
    # ... 现有代码 ...
    
    async def ainvoke(
        self,
        tool_input: Any,
        run_manager: Optional[AsyncCallbackManagerForToolRun] = None,
        **kwargs: Any
    ) -> Any:
        """
        异步调用工具（自动注入 tokenId，并记录到 Langfuse）
        """
        # 从 __dict__ 直接获取 _original_tool，避免触发 __getattr__
        original_tool = self.__dict__.get('_original_tool')
        tool_name = self.__dict__.get('_tool_name', 'unknown_tool')
        
        # 记录工具调用开始
        logger.info(
            f"[TokenInjectedTool] 工具调用开始 - tool_name={tool_name}, "
            f"tool_input_type={type(tool_input).__name__}, tool_input={tool_input}"
        )
        
        # ========== Langfuse Span 创建 ==========
        langfuse_client = get_langfuse_client()
        span_created = False
        
        # 准备工具输入参数（用于记录）
        tool_input_for_log = tool_input
        if isinstance(tool_input, dict):
            if 'args' in tool_input and isinstance(tool_input.get('args'), dict):
                # LangChain 工具调用格式：提取 args
                tool_input_for_log = tool_input.get('args', {})
            else:
                # 直接参数字典格式
                tool_input_for_log = tool_input.copy()
        
        # 准备 Span 参数
        span_params = {
            "name": f"tool_{tool_name}",
            "input": {
                "tool_name": tool_name,
                "tool_input": tool_input_for_log,
            },
            "metadata": {
                "tool_call_id": tool_input.get('id', 'N/A') if isinstance(tool_input, dict) else 'N/A',
                "tool_input_type": type(tool_input).__name__,
            },
        }
        
        # 尝试创建 Span（如果 Langfuse 已启用且可用）
        if (settings.LANGFUSE_ENABLED and 
            settings.LANGFUSE_ENABLE_SPANS and 
            langfuse_client):
            try:
                # 使用 start_as_current_span 创建 Span
                # 如果当前在 LLM Generation 的上下文中，会自动成为子 Span
                span_context = langfuse_client.start_as_current_span(**span_params)
                span_created = True
                logger.debug(
                    f"[TokenInjectedTool] 创建 Langfuse Span: tool_{tool_name}"
                )
            except Exception as e:
                # 错误隔离：Span 创建失败不影响工具执行
                logger.warning(
                    f"[TokenInjectedTool] 创建 Langfuse Span 失败: {e}，继续执行工具"
                )
                span_created = False
        else:
            logger.debug(
                f"[TokenInjectedTool] Langfuse 未启用或不可用，跳过 Span 创建"
            )
        
        # ========== 工具执行 ==========
        try:
            # 如果 tool_input 是字典，需要处理不同的格式
            if isinstance(tool_input, dict):
                # 检查是否是 LangChain 工具调用格式（包含 'args' 字段）
                if 'args' in tool_input and isinstance(tool_input.get('args'), dict):
                    args_dict = tool_input['args'].copy()
                    logger.debug(
                        f"[TokenInjectedTool] 检测到工具调用格式 - tool_name={tool_name}, "
                        f"原始args={args_dict}"
                    )
                    injected_args = self._inject_token_id(args_dict)
                    injected_input = injected_args
                    
                    logger.info(
                        f"[TokenInjectedTool] tokenId 注入完成（工具调用格式） - tool_name={tool_name}, "
                        f"原始args={tool_input['args']}, 注入后args={injected_args}"
                    )
                else:
                    # 直接参数字典格式
                    injected_input = self._inject_token_id(tool_input.copy())
                    logger.debug(
                        f"[TokenInjectedTool] tokenId 注入完成（参数字典格式） - tool_name={tool_name}, "
                        f"injected_input={injected_input}"
                    )
                
                # 执行工具
                result = await original_tool.ainvoke(injected_input, run_manager=run_manager, **kwargs)
                logger.info(
                    f"[TokenInjectedTool] 工具调用成功 - tool_name={tool_name}, "
                    f"result_type={type(result).__name__}, result_length={len(str(result)) if isinstance(result, str) else 'N/A'}"
                )
                
                # ========== 更新 Span（记录输出） ==========
                if span_created:
                    try:
                        # 提取工具输出（用于记录）
                        tool_output = str(result) if isinstance(result, str) else str(result)
                        # 截断过长输出（避免 Langfuse 记录过多数据）
                        tool_output_preview = tool_output[:1000] if len(tool_output) > 1000 else tool_output
                        
                        # 更新 Span 的输出信息
                        # 注意：Langfuse SDK 可能需要在 Span 上下文管理器中更新
                        # 这里我们需要在上下文管理器内部更新，所以需要调整代码结构
                        logger.debug(
                            f"[TokenInjectedTool] 工具执行成功，输出长度: {len(tool_output)}"
                        )
                    except Exception as e:
                        logger.warning(
                            f"[TokenInjectedTool] 更新 Span 输出失败: {e}"
                        )
                
                # 如果结果是字符串，且 tool_input 包含 'id' 字段，包装成 ToolMessage
                if isinstance(result, str) and isinstance(tool_input, dict) and 'id' in tool_input:
                    tool_call_id = tool_input.get('id', '')
                    tool_message = ToolMessage(
                        content=result,
                        tool_call_id=tool_call_id,
                        name=tool_name
                    )
                    logger.debug(
                        f"[TokenInjectedTool] 将字符串结果包装成 ToolMessage - tool_name={tool_name}, "
                        f"tool_call_id={tool_call_id}"
                    )
                    return tool_message
                
                return result
            else:
                # 对于其他类型的输入，直接调用原始工具
                logger.warning(
                    f"[TokenInjectedTool] tool_input 不是字典类型，可能无法注入 tokenId - "
                    f"tool_name={tool_name}, tool_input_type={type(tool_input).__name__}"
                )
                result = await original_tool.ainvoke(tool_input, run_manager=run_manager, **kwargs)
                logger.info(
                    f"[TokenInjectedTool] 工具调用成功 - tool_name={tool_name}, "
                    f"result_type={type(result).__name__}"
                )
                
                # 更新 Span 输出
                if span_created:
                    try:
                        tool_output = str(result) if isinstance(result, str) else str(result)
                        tool_output_preview = tool_output[:1000] if len(tool_output) > 1000 else tool_output
                        logger.debug(
                            f"[TokenInjectedTool] 工具执行成功，输出长度: {len(tool_output)}"
                        )
                    except Exception as e:
                        logger.warning(
                            f"[TokenInjectedTool] 更新 Span 输出失败: {e}"
                        )
                
                # 如果结果是字符串，且 tool_input 包含 'id' 字段
                if isinstance(result, str) and isinstance(tool_input, dict) and 'id' in tool_input:
                    tool_call_id = tool_input.get('id', '')
                    tool_message = ToolMessage(
                        content=result,
                        tool_call_id=tool_call_id,
                        name=tool_name
                    )
                    logger.debug(
                        f"[TokenInjectedTool] 将字符串结果包装成 ToolMessage - tool_name={tool_name}, "
                        f"tool_call_id={tool_call_id}"
                    )
                    return tool_message
                
                return result
                
        except Exception as e:
            # ========== 错误处理：记录到 Span ==========
            logger.error(
                f"[TokenInjectedTool] 工具调用失败 - tool_name={tool_name}, "
                f"error_type={type(e).__name__}, error={str(e)}",
                exc_info=True
            )
            
            # 如果 Span 已创建，记录错误信息
            if span_created:
                try:
                    # 注意：错误信息需要在 Span 上下文管理器中记录
                    # 这里需要在上下文管理器内部处理，所以需要调整代码结构
                    logger.warning(
                        f"[TokenInjectedTool] 工具执行失败，错误: {str(e)}"
                    )
                except Exception as span_error:
                    logger.warning(
                        f"[TokenInjectedTool] 记录错误到 Span 失败: {span_error}"
                    )
            
            raise
        finally:
            # ========== 清理：退出 Span 上下文 ==========
            if span_created:
                try:
                    # 退出上下文管理器（自动完成）
                    pass
                except Exception as e:
                    logger.warning(
                        f"[TokenInjectedTool] 退出 Span 上下文失败: {e}"
                    )
```

**注意**：上面的代码需要在 `with` 语句中使用 `start_as_current_span`，以便正确管理 Span 生命周期。让我们重构代码：

```python
async def ainvoke(
    self,
    tool_input: Any,
    run_manager: Optional[AsyncCallbackManagerForToolRun] = None,
    **kwargs: Any
) -> Any:
    """
    异步调用工具（自动注入 tokenId，并记录到 Langfuse）
    """
    original_tool = self.__dict__.get('_original_tool')
    tool_name = self.__dict__.get('_tool_name', 'unknown_tool')
    
    logger.info(
        f"[TokenInjectedTool] 工具调用开始 - tool_name={tool_name}, "
        f"tool_input_type={type(tool_input).__name__}, tool_input={tool_input}"
    )
    
    # 准备工具输入参数（用于记录）
    tool_input_for_log = tool_input
    if isinstance(tool_input, dict):
        if 'args' in tool_input and isinstance(tool_input.get('args'), dict):
            tool_input_for_log = tool_input.get('args', {}).copy()
        else:
            tool_input_for_log = tool_input.copy()
    
    # ========== Langfuse Span 创建和执行 ==========
    langfuse_client = get_langfuse_client()
    
    # 检查是否启用 Langfuse Span
    if (settings.LANGFUSE_ENABLED and 
        settings.LANGFUSE_ENABLE_SPANS and 
        langfuse_client):
        try:
            # 准备 Span 参数
            span_params = {
                "name": f"tool_{tool_name}",
                "input": {
                    "tool_name": tool_name,
                    "tool_input": tool_input_for_log,
                },
                "metadata": {
                    "tool_call_id": tool_input.get('id', 'N/A') if isinstance(tool_input, dict) else 'N/A',
                    "tool_input_type": type(tool_input).__name__,
                },
            }
            
            # 使用上下文管理器创建 Span
            with langfuse_client.start_as_current_span(**span_params):
                return await self._execute_tool_with_span(
                    original_tool,
                    tool_name,
                    tool_input,
                    run_manager,
                    **kwargs
                )
        except Exception as e:
            # 错误隔离：Span 创建失败不影响工具执行
            logger.warning(
                f"[TokenInjectedTool] 创建 Langfuse Span 失败: {e}，继续执行工具（不记录到 Langfuse）"
            )
            # 不使用 Span，直接执行工具
            return await self._execute_tool_without_span(
                original_tool,
                tool_name,
                tool_input,
                run_manager,
                **kwargs
            )
    else:
        # Langfuse 未启用，直接执行工具
        logger.debug(
            f"[TokenInjectedTool] Langfuse 未启用或不可用，跳过 Span 创建"
        )
        return await self._execute_tool_without_span(
            original_tool,
            tool_name,
            tool_input,
            run_manager,
            **kwargs
        )


async def _execute_tool_with_span(
    self,
    original_tool: BaseTool,
    tool_name: str,
    tool_input: Any,
    run_manager: Optional[AsyncCallbackManagerForToolRun],
    **kwargs: Any
) -> Any:
    """
    在 Langfuse Span 上下文中执行工具
    
    注意：此方法在 Span 上下文管理器中执行，Span 会自动记录执行时间和结果
    """
    try:
        # 处理工具输入并注入 tokenId
        injected_input = self._process_tool_input(tool_input, tool_name)
        
        # 执行工具
        result = await original_tool.ainvoke(injected_input, run_manager=run_manager, **kwargs)
        
        # 记录成功日志
        logger.info(
            f"[TokenInjectedTool] 工具调用成功 - tool_name={tool_name}, "
            f"result_type={type(result).__name__}"
        )
        
        # 处理返回值（可能需要包装成 ToolMessage）
        return self._process_tool_result(result, tool_input, tool_name)
        
    except Exception as e:
        # 记录错误（Span 会自动记录异常）
        logger.error(
            f"[TokenInjectedTool] 工具调用失败 - tool_name={tool_name}, "
            f"error_type={type(e).__name__}, error={str(e)}",
            exc_info=True
        )
        raise


async def _execute_tool_without_span(
    self,
    original_tool: BaseTool,
    tool_name: str,
    tool_input: Any,
    run_manager: Optional[AsyncCallbackManagerForToolRun],
    **kwargs: Any
) -> Any:
    """
    不使用 Langfuse Span 执行工具（向后兼容）
    """
    # 处理工具输入并注入 tokenId
    injected_input = self._process_tool_input(tool_input, tool_name)
    
    # 执行工具
    result = await original_tool.ainvoke(injected_input, run_manager=run_manager, **kwargs)
    
    # 记录成功日志
    logger.info(
        f"[TokenInjectedTool] 工具调用成功 - tool_name={tool_name}, "
        f"result_type={type(result).__name__}"
    )
    
    # 处理返回值
    return self._process_tool_result(result, tool_input, tool_name)


def _process_tool_input(self, tool_input: Any, tool_name: str) -> Any:
    """
    处理工具输入，注入 tokenId
    """
    if isinstance(tool_input, dict):
        if 'args' in tool_input and isinstance(tool_input.get('args'), dict):
            # LangChain 工具调用格式
            args_dict = tool_input['args'].copy()
            injected_args = self._inject_token_id(args_dict)
            logger.info(
                f"[TokenInjectedTool] tokenId 注入完成（工具调用格式） - tool_name={tool_name}, "
                f"原始args={tool_input['args']}, 注入后args={injected_args}"
            )
            return injected_args
        else:
            # 直接参数字典格式
            injected_input = self._inject_token_id(tool_input.copy())
            logger.debug(
                f"[TokenInjectedTool] tokenId 注入完成（参数字典格式） - tool_name={tool_name}"
            )
            return injected_input
    else:
        logger.warning(
            f"[TokenInjectedTool] tool_input 不是字典类型，可能无法注入 tokenId - "
            f"tool_name={tool_name}, tool_input_type={type(tool_input).__name__}"
        )
        return tool_input


def _process_tool_result(self, result: Any, tool_input: Any, tool_name: str) -> Any:
    """
    处理工具返回值，必要时包装成 ToolMessage
    """
    if isinstance(result, str) and isinstance(tool_input, dict) and 'id' in tool_input:
        tool_call_id = tool_input.get('id', '')
        tool_message = ToolMessage(
            content=result,
            tool_call_id=tool_call_id,
            name=tool_name
        )
        logger.debug(
            f"[TokenInjectedTool] 将字符串结果包装成 ToolMessage - tool_name={tool_name}, "
            f"tool_call_id={tool_call_id}"
        )
        return tool_message
    
    return result
```

#### 步骤 2：优化 Span 输出记录

**需求**：在 Span 中记录工具的输出结果和错误信息

**实现**：Langfuse SDK 的 `start_as_current_span` 返回的上下文管理器可能支持更新输出。我们需要在 Span 上下文中更新：

```python
# 在 _execute_tool_with_span 中
async def _execute_tool_with_span(
    self,
    original_tool: BaseTool,
    tool_name: str,
    tool_input: Any,
    run_manager: Optional[AsyncCallbackManagerForToolRun],
    **kwargs: Any
) -> Any:
    try:
        injected_input = self._process_tool_input(tool_input, tool_name)
        result = await original_tool.ainvoke(injected_input, run_manager=run_manager, **kwargs)
        
        # 尝试更新 Span 输出
        try:
            from langfuse import get_current_trace
            current_trace = get_current_trace()
            if current_trace:
                # 提取输出（截断过长内容）
                output_preview = str(result)[:1000] if len(str(result)) > 1000 else str(result)
                # 更新当前 Span 的输出
                # 注意：需要根据 Langfuse SDK 的实际 API 调整
                # Langfuse 3.x 可能支持直接更新
                logger.debug(f"[TokenInjectedTool] 工具执行成功，输出已记录到 Span")
        except Exception as e:
            logger.debug(f"[TokenInjectedTool] 更新 Span 输出失败: {e}")
        
        return self._process_tool_result(result, tool_input, tool_name)
    except Exception as e:
        # 错误会自动记录到 Span（通过异常抛出）
        logger.error(f"[TokenInjectedTool] 工具调用失败: {e}", exc_info=True)
        raise
```

**注意**：根据 Langfuse SDK 的实际版本，可能需要调整更新输出的方式。建议查看 Langfuse SDK 文档。

#### 步骤 3：测试验证

**测试点**：
1. ✅ 工具执行 Span 是否成功创建
2. ✅ Span 是否作为 LLM Generation 的子节点
3. ✅ 工具输入参数是否正确记录
4. ✅ 工具输出结果是否正确记录
5. ✅ 错误信息是否正确记录
6. ✅ 执行时间是否正确记录

**测试代码**：

```python
# cursor_test/tools/test_tool_langfuse_span.py

import pytest
from domain.tools.wrapper import TokenInjectedTool, wrap_tools_with_token_context
from domain.tools.context import TokenContext
from infrastructure.observability.langfuse_handler import get_langfuse_client
from app.core.config import settings

async def test_tool_span_creation():
    """测试工具执行时是否创建 Langfuse Span"""
    # ... 测试代码 ...
    pass

async def test_tool_span_nested():
    """测试工具 Span 是否嵌套在 LLM Generation 下"""
    # ... 测试代码 ...
    pass

async def test_tool_span_with_error():
    """测试工具执行失败时错误信息是否正确记录"""
    # ... 测试代码 ...
    pass
```

## 四、扩展方案：二级、三级节点

### 4.1 数据库操作 Span（二级节点）

**目标**：在工具执行 Span 下，为数据库操作创建子 Span

**实现位置**：`infrastructure/database/repository/*.py` 或工具实现中

**示例代码**：

```python
# domain/tools/blood_pressure/record.py

from infrastructure.observability.langfuse_handler import get_langfuse_client
from app.core.config import settings

async def record_blood_pressure(
    systolic: int,
    diastolic: int,
    # ... 其他参数
    token_id: str = ""
) -> str:
    """记录血压数据到数据库"""
    
    langfuse_client = get_langfuse_client()
    
    # 创建数据库操作 Span（作为工具执行 Span 的子节点）
    if (settings.LANGFUSE_ENABLED and 
        settings.LANGFUSE_ENABLE_SPANS and 
        langfuse_client):
        with langfuse_client.start_as_current_span(
            name="db_operation",
            input={
                "operation": "create",
                "table": "blood_pressure",
                "data": {
                    "systolic": systolic,
                    "diastolic": diastolic,
                    # ... 其他字段
                }
            },
            metadata={
                "repository": "BloodPressureRepository",
            }
        ):
            # 执行数据库操作
            session = get_async_session_factory()()
            try:
                repo = BloodPressureRepository(session)
                record = await repo.create(...)
                await session.commit()
                
                return f"成功记录血压：..."
            except Exception as e:
                await session.rollback()
                raise
            finally:
                await session.close()
    else:
        # 不使用 Span，直接执行
        # ... 原有代码 ...
```

### 4.2 外部服务调用 Span（三级节点）

**目标**：在数据库操作 Span 下，为外部服务调用创建子 Span

**实现位置**：`infrastructure/external/*.py`

**示例代码**：

```python
# infrastructure/external/java_service.py

from infrastructure.observability.langfuse_handler import get_langfuse_client
from app.core.config import settings

async def call_java_service(endpoint: str, data: dict):
    """调用外部 Java 服务"""
    
    langfuse_client = get_langfuse_client()
    
    # 创建外部服务调用 Span（作为当前活动 Span 的子节点）
    if (settings.LANGFUSE_ENABLED and 
        settings.LANGFUSE_ENABLE_SPANS and 
        langfuse_client):
        with langfuse_client.start_as_current_span(
            name="external_api",
            input={
                "service": "java_service",
                "endpoint": endpoint,
                "request_data": data,
            },
            metadata={
                "service_type": "http",
                "timeout": 30,
            }
        ):
            # 执行 HTTP 请求
            response = await http_client.post(endpoint, json=data)
            return response.json()
    else:
        # 不使用 Span，直接执行
        # ... 原有代码 ...
```

### 4.3 层级结构示例

**完整的层级结构**：

```
Trace (chat_request)
  └─ Span (agent_blood_pressure_agent)              # 一级：Agent 节点
      └─ Generation (LLM 调用)                      # LLM Generation
          └─ Span (tool_record_blood_pressure)      # 二级：工具执行
              ├─ Span (db_operation)                # 三级：数据库操作
              │   ├─ Span (db_query)                # 四级：数据库查询
              │   └─ Span (db_insert)               # 四级：数据库插入
              └─ Span (external_api)                # 三级：外部服务调用
                  └─ Span (http_request)            # 四级：HTTP 请求
```

**实现原则**：
1. 每个层级使用 `start_as_current_span` 创建 Span
2. 在父 Span 的上下文中创建子 Span，自动形成嵌套关系
3. 使用上下文管理器确保 Span 生命周期正确管理
4. 错误隔离：Span 创建失败不影响业务逻辑

## 五、配置说明

### 5.1 环境变量配置

**现有配置**（`app/core/config.py`）：
- `LANGFUSE_ENABLED`：是否启用 Langfuse
- `LANGFUSE_ENABLE_SPANS`：是否启用 Span 追踪
- `LANGFUSE_PUBLIC_KEY`：Langfuse 公钥
- `LANGFUSE_SECRET_KEY`：Langfuse 密钥
- `LANGFUSE_HOST`：Langfuse 服务地址

**无需新增配置**：工具 Span 追踪使用现有的 Span 配置。

### 5.2 代码配置

**启用工具 Span 追踪**：
- 确保 `LANGFUSE_ENABLED=True`
- 确保 `LANGFUSE_ENABLE_SPANS=True`
- 工具 Span 追踪会自动启用（无需额外配置）

**禁用工具 Span 追踪**：
- 设置 `LANGFUSE_ENABLE_SPANS=False`（禁用所有 Span 追踪）
- 或设置 `LANGFUSE_ENABLED=False`（完全禁用 Langfuse）

## 六、注意事项

### 6.1 性能影响

**潜在影响**：
- 每次工具调用都会创建 Span，可能增加少量开销
- Span 数据会异步发送到 Langfuse，不影响主流程性能

**优化建议**：
- 使用批量发送（`LANGFUSE_FLUSH_AT`）
- 使用异步发送（默认行为）
- 避免在 Span 中记录过多数据（截断长字符串）

### 6.2 错误隔离

**原则**：
- Span 创建失败不应影响工具执行
- 使用 try-except 包裹 Span 创建逻辑
- 记录警告日志，但不抛出异常

### 6.3 数据隐私

**注意事项**：
- 工具输入参数可能包含敏感信息（如用户数据）
- 考虑在 Span 中脱敏或过滤敏感字段
- 可以通过 `metadata` 记录摘要信息，而不是完整数据

**建议**：
```python
# 在工具 Span 创建时，过滤敏感字段
span_params = {
    "name": f"tool_{tool_name}",
    "input": {
        "tool_name": tool_name,
        # 只记录非敏感字段
        "systolic": tool_input.get("systolic"),
        "diastolic": tool_input.get("diastolic"),
        # 不记录 token_id 等敏感信息
    },
    "metadata": {
        "has_token_id": "token_id" in tool_input,
        # ... 其他元数据
    },
}
```

### 6.4 Langfuse SDK 版本兼容性

**注意事项**：
- Langfuse SDK API 可能因版本而异
- 建议测试不同版本的兼容性
- 参考 Langfuse 官方文档

**当前版本**：`langfuse>=3.0.0,<4.0.0`（`requirements.txt`）

## 七、实施计划

### 7.1 第一阶段：工具执行 Span（当前任务）

**任务**：
1. ✅ 在 `TokenInjectedTool.ainvoke()` 中集成 Langfuse Span
2. ✅ 记录工具输入参数
3. ✅ 记录工具输出结果
4. ✅ 记录错误信息
5. ✅ 测试验证

**预计工作量**：2-3 小时

### 7.2 第二阶段：数据库操作 Span（后续扩展）

**任务**：
1. 在数据库 Repository 中集成 Langfuse Span
2. 记录 SQL 查询信息
3. 记录数据库操作结果
4. 测试验证

**预计工作量**：3-4 小时

### 7.3 第三阶段：外部服务调用 Span（后续扩展）

**任务**：
1. 在外部服务调用中集成 Langfuse Span
2. 记录 HTTP 请求信息
3. 记录响应结果
4. 测试验证

**预计工作量**：2-3 小时

## 八、总结

通过以上方案，可以实现：

1. ✅ **工具执行信息记录**：在工具执行时创建 Langfuse Span，记录详细的执行信息
2. ✅ **层级关系**：工具执行 Span 自动成为 LLM Generation 的子节点
3. ✅ **可扩展性**：支持后续添加二级、三级节点（数据库操作、外部服务调用等）
4. ✅ **错误隔离**：Span 创建失败不影响业务逻辑
5. ✅ **性能优化**：使用异步发送和批量发送，最小化性能影响

**关键实现点**：
- 使用 `start_as_current_span` 创建嵌套 Span
- 在父 Span 的上下文中创建子 Span，自动形成层级关系
- 使用上下文管理器确保 Span 生命周期正确管理
- 错误隔离和日志记录

**下一步行动**：
1. 实施第一阶段：工具执行 Span
2. 测试验证功能正确性
3. 根据需要扩展二级、三级节点

