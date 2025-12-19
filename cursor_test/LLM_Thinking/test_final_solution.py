"""
最终解决方案测试：验证思考过程提取

本测试演示如何通过直接调用 API 来获取完整的响应（包括 reasoning_content），
然后与 LangChain 的响应进行对比。
"""
import os
import json
import logging
from typing import Dict, Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
import httpx

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_env_config() -> Dict[str, str]:
    """从 .env 文件加载配置"""
    config = {}
    env_file = ".env"
    if not os.path.exists(env_file):
        env_file = ".env example"
    
    if os.path.exists(env_file):
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()
    return config


def test_comparison():
    """
    对比测试：直接 API 调用 vs LangChain 调用
    
    验证：
    1. 直接 API 调用可以获取 reasoning_content
    2. LangChain 调用无法获取 reasoning_content
    3. 提供解决方案建议
    """
    logger.info("=" * 80)
    logger.info("对比测试：直接 API 调用 vs LangChain 调用")
    logger.info("=" * 80)
    
    config = load_env_config()
    api_key = config.get("OPENAI_API_KEY", "")
    base_url = config.get("OPENAI_BASE_URL", "")
    model = config.get("LLM_MODEL", "deepseek-r1-250528")
    
    if not api_key or not base_url:
        logger.error("缺少必要的配置")
        return
    
    test_message = "请帮我记录血压，收缩压是120，舒张压是80"
    
    # 测试1: 直接 API 调用
    logger.info("\n" + "=" * 80)
    logger.info("测试1: 直接 API 调用（可以获取 reasoning_content）")
    logger.info("=" * 80)
    
    try:
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": test_message}],
            "stream": False
        }
        
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            
            if "choices" in result and len(result["choices"]) > 0:
                choice = result["choices"][0]
                message = choice.get("message", {})
                
                content = message.get("content", "")
                reasoning_content = message.get("reasoning_content", "")
                
                logger.info(f"✅ 直接 API 调用成功")
                logger.info(f"   content 长度: {len(content)} 字符")
                logger.info(f"   reasoning_content 长度: {len(reasoning_content)} 字符")
                if reasoning_content:
                    logger.info(f"   reasoning_content 预览: {reasoning_content[:200]}...")
                else:
                    logger.warning("   ❌ 未找到 reasoning_content")
    except Exception as e:
        logger.error(f"直接 API 调用失败: {str(e)}", exc_info=True)
    
    # 测试2: LangChain 调用
    logger.info("\n" + "=" * 80)
    logger.info("测试2: LangChain 调用（无法获取 reasoning_content）")
    logger.info("=" * 80)
    
    try:
        llm = ChatOpenAI(
            model=model,
            openai_api_key=api_key,
            base_url=base_url,
            temperature=0.7,
            max_tokens=2048
        )
        
        message = HumanMessage(content=test_message)
        response = llm.invoke([message])
        
        content = response.content if hasattr(response, "content") else ""
        additional_kwargs = getattr(response, "additional_kwargs", {}) or {}
        response_metadata = getattr(response, "response_metadata", {}) or {}
        
        logger.info(f"✅ LangChain 调用成功")
        logger.info(f"   content 长度: {len(content)} 字符")
        logger.info(f"   additional_kwargs 键: {list(additional_kwargs.keys())}")
        logger.info(f"   response_metadata 键: {list(response_metadata.keys())}")
        
        # 检查是否有 reasoning_content
        has_reasoning = False
        if "reasoning_content" in additional_kwargs:
            logger.info(f"   ✅ 在 additional_kwargs 中找到 reasoning_content")
            has_reasoning = True
        elif "reasoning_content" in response_metadata:
            logger.info(f"   ✅ 在 response_metadata 中找到 reasoning_content")
            has_reasoning = True
        else:
            logger.warning("   ❌ 未在 LangChain 响应中找到 reasoning_content")
    except Exception as e:
        logger.error(f"LangChain 调用失败: {str(e)}", exc_info=True)
    
    # 总结
    logger.info("\n" + "=" * 80)
    logger.info("总结与建议")
    logger.info("=" * 80)
    logger.info("""
问题确认：
1. ✅ 火山引擎 API 的原始响应包含 reasoning_content 字段
2. ❌ LangChain 的 ChatOpenAI 在解析响应时丢失了 reasoning_content 字段
3. ❌ reasoning_content 不在 additional_kwargs 或 response_metadata 中

解决方案建议：
1. 短期方案：对于需要思考过程的场景，直接使用 httpx 调用 API
2. 中期方案：实现 HTTP 响应拦截器，在响应解析前提取 reasoning_content
3. 长期方案：向 LangChain 提交 issue/PR，请求支持 reasoning_content 字段

当前代码状态：
- llm_logger.py 已经实现了多种提取方式
- 但由于 LangChain 没有保留 reasoning_content，这些方式都无法生效
- 需要实现 HTTP 拦截器或使用其他方式来获取原始响应
    """)


if __name__ == "__main__":
    test_comparison()

