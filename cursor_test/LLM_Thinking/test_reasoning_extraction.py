"""
测试 DeepSeek R1 模型的思考过程提取

本测试用于验证：
1. 火山引擎 API 返回的原始响应格式
2. LangChain ChatOpenAI 如何处理响应
3. 如何正确提取思考过程（reasoning_content）
"""
import os
import json
import logging
from typing import Any, Dict, Optional

import httpx
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage

# 配置日志
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


def test_direct_api_call():
    """
    测试1: 直接调用火山引擎 API，查看原始响应格式
    """
    logger.info("=" * 80)
    logger.info("测试1: 直接调用火山引擎 API")
    logger.info("=" * 80)
    
    config = load_env_config()
    api_key = config.get("OPENAI_API_KEY", "")
    base_url = config.get("OPENAI_BASE_URL", "")
    model = config.get("LLM_MODEL", "deepseek-r1-250528")
    
    if not api_key or not base_url:
        logger.error("缺少必要的配置：OPENAI_API_KEY 或 OPENAI_BASE_URL")
        return
    
    # 构建请求
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "请帮我记录血压，收缩压是120，舒张压是80"
            }
        ],
        "stream": False
    }
    
    logger.info(f"请求 URL: {url}")
    logger.info(f"请求模型: {model}")
    logger.info(f"请求内容: {json.dumps(payload, ensure_ascii=False, indent=2)}")
    
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            
            result = response.json()
            
            logger.info("=" * 80)
            logger.info("原始 API 响应:")
            logger.info("=" * 80)
            logger.info(json.dumps(result, ensure_ascii=False, indent=2))
            
            # 分析响应结构
            logger.info("=" * 80)
            logger.info("响应结构分析:")
            logger.info("=" * 80)
            
            if "choices" in result and len(result["choices"]) > 0:
                choice = result["choices"][0]
                message = choice.get("message", {})
                
                logger.info(f"消息类型: {type(message)}")
                logger.info(f"消息内容类型: {type(message.get('content'))}")
                
                content = message.get("content")
                if isinstance(content, str):
                    logger.info(f"内容格式: 字符串")
                    logger.info(f"内容长度: {len(content)}")
                    # 检查是否包含 <think> 标签
                    if "<think>" in content or "</think>" in content:
                        logger.info("✅ 检测到 <think> 标签")
                    else:
                        logger.info("❌ 未检测到 <think> 标签")
                elif isinstance(content, list):
                    logger.info(f"内容格式: 列表（结构化内容）")
                    logger.info(f"列表长度: {len(content)}")
                    for i, item in enumerate(content):
                        logger.info(f"  项目 {i}: 类型={type(item)}, 内容={json.dumps(item, ensure_ascii=False)[:200]}")
                
                # 检查其他可能的字段
                logger.info(f"消息的所有键: {list(message.keys())}")
                for key in message.keys():
                    if key not in ["role", "content"]:
                        logger.info(f"  额外字段 {key}: {type(message[key])} = {str(message[key])[:200]}")
            
            # 检查 usage 信息
            if "usage" in result:
                logger.info(f"Token 使用: {result['usage']}")
            
            return result
            
    except Exception as e:
        logger.error(f"API 调用失败: {str(e)}", exc_info=True)
        return None


def test_langchain_response():
    """
    测试2: 使用 LangChain ChatOpenAI 调用，查看响应对象结构
    """
    logger.info("=" * 80)
    logger.info("测试2: 使用 LangChain ChatOpenAI 调用")
    logger.info("=" * 80)
    
    config = load_env_config()
    api_key = config.get("OPENAI_API_KEY", "")
    base_url = config.get("OPENAI_BASE_URL", "")
    model = config.get("LLM_MODEL", "deepseek-r1-250528")
    
    if not api_key or not base_url:
        logger.error("缺少必要的配置：OPENAI_API_KEY 或 OPENAI_BASE_URL")
        return
    
    try:
        # 创建 LangChain 客户端
        llm = ChatOpenAI(
            model=model,
            openai_api_key=api_key,
            base_url=base_url,
            temperature=0.7,
            max_tokens=2048
        )
        
        # 调用模型
        message = HumanMessage(content="请帮我记录血压，收缩压是120，舒张压是80")
        logger.info(f"发送消息: {message.content}")
        
        response = llm.invoke([message])
        
        logger.info("=" * 80)
        logger.info("LangChain 响应对象分析:")
        logger.info("=" * 80)
        
        logger.info(f"响应类型: {type(response)}")
        logger.info(f"响应类名: {response.__class__.__name__}")
        
        # 检查 content 属性
        if hasattr(response, "content"):
            content = response.content
            logger.info(f"content 类型: {type(content)}")
            logger.info(f"content 值: {str(content)[:500]}")
            
            if isinstance(content, list):
                logger.info("✅ content 是列表（结构化内容）")
                for i, item in enumerate(content):
                    logger.info(f"  项目 {i}: {type(item)} = {json.dumps(item, ensure_ascii=False, default=str)[:300]}")
            elif isinstance(content, str):
                logger.info("content 是字符串")
                if "<think>" in content or "</think>" in content:
                    logger.info("✅ 检测到 <think> 标签")
                else:
                    logger.info("❌ 未检测到 <think> 标签")
        
        # 检查 additional_kwargs
        if hasattr(response, "additional_kwargs"):
            additional_kwargs = response.additional_kwargs
            logger.info(f"additional_kwargs 类型: {type(additional_kwargs)}")
            logger.info(f"additional_kwargs 键: {list(additional_kwargs.keys()) if additional_kwargs else []}")
            if additional_kwargs:
                for key, value in additional_kwargs.items():
                    logger.info(f"  {key}: {type(value)} = {str(value)[:200]}")
        
        # 检查所有属性
        logger.info("=" * 80)
        logger.info("响应对象的所有属性:")
        logger.info("=" * 80)
        for attr in dir(response):
            if not attr.startswith("_"):
                try:
                    value = getattr(response, attr)
                    if not callable(value):
                        logger.info(f"  {attr}: {type(value)} = {str(value)[:200]}")
                except:
                    pass
        
        return response
        
    except Exception as e:
        logger.error(f"LangChain 调用失败: {str(e)}", exc_info=True)
        return None


def extract_reasoning_from_response(response: Any) -> Optional[str]:
    """
    从响应中提取思考过程
    
    尝试多种方式提取思考过程：
    1. 从结构化 content 列表中提取 reasoning 类型的块
    2. 从字符串 content 中提取 <think> 标签内容
    3. 从 additional_kwargs 中提取
    """
    logger.info("=" * 80)
    logger.info("提取思考过程:")
    logger.info("=" * 80)
    
    reasoning_content = None
    
    if not response:
        logger.warning("响应对象为空")
        return None
    
    # 方法1: 检查 content 属性
    if hasattr(response, "content"):
        content = response.content
        
        # 情况1: content 是列表（结构化内容）
        if isinstance(content, list):
            logger.info("检测到结构化内容（列表格式）")
            reasoning_parts = []
            text_parts = []
            
            for block in content:
                if isinstance(block, dict):
                    block_type = block.get("type", "")
                    logger.info(f"  块类型: {block_type}")
                    
                    if block_type == "reasoning":
                        logger.info("  ✅ 找到 reasoning 类型的块")
                        # 提取 reasoning 内容
                        summary = block.get("summary", [])
                        if summary:
                            logger.info(f"    有 summary 字段，长度: {len(summary)}")
                            for summary_item in summary:
                                if isinstance(summary_item, dict):
                                    text = summary_item.get("text", "")
                                    reasoning_parts.append(text)
                                    logger.info(f"    提取到 reasoning 文本: {text[:100]}")
                                else:
                                    reasoning_parts.append(str(summary_item))
                                    logger.info(f"    提取到 reasoning 文本: {str(summary_item)[:100]}")
                        
                        # 如果没有 summary，尝试直接获取 text
                        if not reasoning_parts and "text" in block:
                            text = block.get("text", "")
                            reasoning_parts.append(text)
                            logger.info(f"    从 text 字段提取: {text[:100]}")
                    elif block_type == "text":
                        text = block.get("text", "")
                        text_parts.append(text)
                        logger.info(f"  找到 text 类型的块: {text[:100]}")
                    else:
                        logger.info(f"  未知块类型: {block_type}")
                else:
                    logger.info(f"  非字典块: {type(block)}")
            
            if reasoning_parts:
                reasoning_content = "\n".join(reasoning_parts)
                logger.info(f"✅ 成功提取思考过程（从结构化内容）: {len(reasoning_content)} 字符")
            else:
                logger.info("❌ 未在结构化内容中找到 reasoning 块")
        
        # 情况2: content 是字符串
        elif isinstance(content, str):
            logger.info("检测到字符串内容")
            # 尝试从 <think> 标签中提取
            import re
            think_pattern = r'<think>(.*?)</think>'
            think_matches = re.findall(think_pattern, content, re.DOTALL)
            
            if think_matches:
                reasoning_content = "\n".join(think_matches)
                logger.info(f"✅ 成功提取思考过程（从 <think> 标签）: {len(reasoning_content)} 字符")
            else:
                logger.info("❌ 未在字符串内容中找到 <think> 标签")
    
    # 方法2: 检查 additional_kwargs
    if not reasoning_content and hasattr(response, "additional_kwargs"):
        additional_kwargs = response.additional_kwargs or {}
        logger.info("检查 additional_kwargs")
        
        # 检查常见的思考过程字段名
        possible_keys = [
            "reasoning", "thinking", "thought", 
            "reasoning_content", "thinking_content",
            "reasoning_text", "thinking_text"
        ]
        
        for key in possible_keys:
            if key in additional_kwargs:
                reasoning_content = additional_kwargs[key]
                logger.info(f"✅ 从 additional_kwargs['{key}'] 提取思考过程")
                break
        
        # 如果没有找到，检查所有键
        if not reasoning_content:
            for key in additional_kwargs.keys():
                if any(term in key.lower() for term in ["reason", "think", "thought"]):
                    reasoning_content = additional_kwargs[key]
                    logger.info(f"✅ 从 additional_kwargs['{key}'] 提取思考过程")
                    break
    
    if reasoning_content:
        logger.info("=" * 80)
        logger.info("提取到的思考过程:")
        logger.info("=" * 80)
        logger.info(reasoning_content)
    else:
        logger.warning("❌ 未能提取到思考过程")
    
    return reasoning_content


def test_reasoning_extraction():
    """
    测试3: 完整测试思考过程提取流程
    """
    logger.info("=" * 80)
    logger.info("测试3: 完整测试思考过程提取")
    logger.info("=" * 80)
    
    # 先测试直接 API 调用
    api_response = test_direct_api_call()
    
    # 再测试 LangChain 调用
    langchain_response = test_langchain_response()
    
    # 尝试从 LangChain 响应中提取思考过程
    if langchain_response:
        reasoning = extract_reasoning_from_response(langchain_response)
        
        if reasoning:
            logger.info("=" * 80)
            logger.info("✅ 成功提取思考过程！")
            logger.info("=" * 80)
        else:
            logger.info("=" * 80)
            logger.info("❌ 未能提取思考过程")
            logger.info("=" * 80)
            logger.info("可能的原因：")
            logger.info("1. API 响应格式与预期不符")
            logger.info("2. 需要特定的参数来启用思考过程输出")
            logger.info("3. LangChain 的响应处理可能丢失了思考过程信息")
            logger.info("=" * 80)


if __name__ == "__main__":
    test_reasoning_extraction()

