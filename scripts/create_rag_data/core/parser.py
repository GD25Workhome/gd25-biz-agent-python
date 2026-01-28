"""
从模型输出文本中抽取 JSON 并解析为 cases 列表。
"""
import json
import logging
import re
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def _extract_json_text(text: str) -> Optional[str]:
    """
    从文本中抽取第一个完整 JSON 对象（可先去掉 ```json ... ``` 包裹）。

    Returns:
        抽取出的 JSON 字符串，失败返回 None。
    """
    if not text or not text.strip():
        return None
    s = text.strip()
    # 去掉 markdown 代码块
    code_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", s, re.IGNORECASE)
    if code_block:
        s = code_block.group(1).strip()
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None


def parse_cases_from_model_output(text: str) -> List[Dict[str, Any]]:
    """
    从模型输出文本中解析出 cases 数组。

    支持 ```json ... ``` 包裹及前后噪音；只解析根对象的 cases 键。

    Args:
        text: 模型返回的完整文本。

    Returns:
        cases 列表；解析失败返回空列表（并打日志）。
    """
    json_str = _extract_json_text(text)
    if not json_str:
        logger.warning("未能从模型输出中抽取到 JSON，长度=%d", len(text or ""))
        return []

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.warning("JSON 解析失败: %s，片段=%s", e, (json_str[:200] + "..." if len(json_str) > 200 else json_str))
        return []

    if not isinstance(data, dict):
        logger.warning("根对象不是 dict: %s", type(data))
        return []

    cases = data.get("cases")
    if not isinstance(cases, list):
        logger.warning("cases 不是 list: %s", type(cases))
        return []

    return cases
