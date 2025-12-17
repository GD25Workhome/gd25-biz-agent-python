"""
LLM 客户端测试
测试火山引擎模型连通性

Pytest 命令示例：
================

# 运行整个测试文件
pytest cursor_test/M1_test/infrastructure/test_llm_client.py

# 运行整个测试文件（详细输出）
pytest cursor_test/M1_test/infrastructure/test_llm_client.py -v
# （详细输出 + 显示 print 输出）
pytest cursor_test/M1_test/infrastructure/test_llm_client.py -v -s

# 运行特定的测试方法
pytest cursor_test/M1_test/infrastructure/test_llm_client.py::TestLLMClient::test_volcengine_connection
"""
import pytest
from langchain_core.messages import HumanMessage

from infrastructure.llm.client import get_llm
from app.core.config import settings


class TestLLMClient:
    """LLM 客户端测试类"""
    
    @pytest.mark.asyncio
    async def test_volcengine_connection(self):
        """
        测试用例：验证火山引擎 API 连通性
        
        验证：
        - 能够成功创建 LLM 客户端实例
        - 能够正常连接到火山引擎 API
        - 能够成功调用 API 并获取响应
        """
        # Arrange（准备）
        # 使用配置中的火山引擎配置
        # 配置来源：.env 文件
        # OPENAI_API_KEY=48bafa4f-***-ca2e2f755522
        # OPENAI_BASE_URL=https://ark.cn-beijing.volces.com/api/v3/chat/completions
        # LLM_MODEL=doubao-seed-1-6-251015
        # LLM_TEMPERATURE=0.7
        
        # Act（执行）
        # 使用配置中的默认值创建 LLM 实例
        llm = get_llm()
        
        # 验证 LLM 实例创建成功
        assert llm is not None
        
        # 发送测试消息
        messages = [HumanMessage(content="你好，请回复'测试成功'")]
        response = await llm.ainvoke(messages)
        
        # Assert（断言）
        # 验证响应不为空
        assert response is not None
        assert hasattr(response, 'content')
        assert response.content is not None
        assert len(response.content) > 0
        
        # 打印响应内容（用于调试）
        print(f"\n✅ 火山引擎 API 连通性测试成功")
        print(f"📝 模型: {settings.LLM_MODEL}")
        print(f"🌡️  温度: {settings.LLM_TEMPERATURE}")
        print(f"🔗 Base URL: {settings.OPENAI_BASE_URL}")
        print(f"💬 响应内容: {response.content[:200]}...")  # 只打印前200个字符
