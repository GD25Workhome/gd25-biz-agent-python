"""
华院联通聊天相关 Schema
"""
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class HuayuanChatRequest(BaseModel):
    """华院联通聊天请求（无 Session）。"""

    query: str = Field(..., description="用户本轮输入")
    trace_id: Optional[str] = Field(
        default=None,
        description="Trace ID（可选，32位小写十六进制；未提供则服务端自动生成）",
    )

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        """
            校验 query 去除首尾空白后非空。

            Args:
                value: 原始 query 字符串

            Returns:
                去除首尾空白后的 query

            Raises:
                ValueError: query 为空或仅含空白
        """
        stripped = value.strip() if isinstance(value, str) else ""
        if not stripped:
            raise ValueError("query 不能为空")
        return stripped


class HuayuanChatResponse(BaseModel):
    """华院联通聊天响应。"""

    response: str = Field(description="助手回复")
    trace_id: str = Field(description="本次实际使用的 Trace ID")
