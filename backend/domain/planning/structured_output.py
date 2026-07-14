"""
Plan-and-Execute 结构化 LLM 调用封装
"""
import json
import logging
import re
from typing import List, Optional, Type, TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _extract_json_object(text: str) -> str:
    """从文本中提取第一个 JSON 对象子串。"""
    text = text.strip()
    if text.startswith("{"):
        depth = 0
        in_string = False
        escape = False
        quote = '"'
        for i, c in enumerate(text):
            if escape:
                escape = False
                continue
            if c == "\\" and in_string:
                escape = True
                continue
            if not in_string:
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        return text[: i + 1]
                elif c == '"':
                    in_string = True
            else:
                if c == quote:
                    in_string = False
    return text


def _parse_json_to_model(text: str, schema: Type[T]) -> T:
    """
    从文本解析 JSON 并校验为 Pydantic 模型。

    Args:
        text: 含 JSON 的文本
        schema: 目标 Pydantic 模型类

    Returns:
        T: 解析后的模型实例

    Raises:
        ValueError: 解析或校验失败
    """
    raw = text.strip()
    if not raw:
        raise ValueError("LLM 输出为空")

    # 去除 markdown 代码块包裹
    code_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if code_block:
        raw = code_block.group(1).strip()

    candidates = [raw, _extract_json_object(raw)]
    last_error: Optional[Exception] = None
    for candidate in candidates:
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
            return schema.model_validate(data)
        except (json.JSONDecodeError, ValidationError, TypeError) as e:
            last_error = e
            continue

    raise ValueError(f"无法解析为 {schema.__name__}: {last_error}")


async def invoke_structured_llm(
    llm: BaseChatModel,
    schema: Type[T],
    messages: List[BaseMessage],
) -> T:
    """
    调用 LLM 并返回结构化 Pydantic 结果。

    优先使用 with_structured_output；失败时 fallback 到普通 invoke + JSON 解析。

    Args:
        llm: LangChain 聊天模型
        schema: 目标 Pydantic 模型类
        messages: 消息列表

    Returns:
        T: 结构化输出

    Raises:
        ValueError: 两种方式均失败
    """
    # 1. 尝试原生结构化输出
    try:
        structured_llm = llm.with_structured_output(schema)
        result = await structured_llm.ainvoke(messages)
        if isinstance(result, schema):
            return result
        if isinstance(result, dict):
            return schema.model_validate(result)
    except Exception as e:
        logger.warning(
            "with_structured_output 失败，将 fallback 到 JSON 解析: schema=%s, error=%s",
            schema.__name__,
            e,
        )

    # 2. Fallback：普通调用 + JSON 解析
    response = await llm.ainvoke(messages)
    content = getattr(response, "content", None)
    if content is None:
        raise ValueError(f"LLM 响应无 content: {schema.__name__}")

    if isinstance(content, dict):
        return schema.model_validate(content)

    return _parse_json_to_model(str(content), schema)
