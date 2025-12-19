"""
测试 LangChain 响应中的 metadata 和 llm_output

检查 reasoning_content 是否存储在 response_metadata 或 llm_output 中
"""
import os
import json
import logging
from typing import Any, Dict

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ResponseCaptureHandler(BaseCallbackHandler):
    """捕获原始响应的回调处理器"""
    
    def __init__(self):
        self.raw_response = None
        self.llm_output = None
        self.response_metadata = None
    
    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """捕获响应数据"""
        logger.info("=" * 80)
        logger.info("回调处理器捕获的响应:")
        logger.info("=" * 80)
        
        # 检查 llm_output
        if hasattr(response, "llm_output"):
            self.llm_output = response.llm_output
            logger.info("llm_output 类型: " + str(type(self.llm_output)))
            logger.info("llm_output 内容:")
            logger.info(json.dumps(self.llm_output, ensure_ascii=False, indent=2, default=str))
        
        # 检查 generations
        if hasattr(response, "generations"):
            generations = response.generations
            logger.info(f"generations 数量: {len(generations)}")
            
            if generations and len(generations) > 0:
                generation = generations[0]
                if generation and len(generation) > 0:
                    gen_obj = generation[0]
                    logger.info(f"generation 类型: {type(gen_obj)}")
                    
                    # 检查 message
                    if hasattr(gen_obj, "message"):
                        message = gen_obj.message
                        logger.info(f"message 类型: {type(message)}")
                        
                        # 检查 response_metadata
                        if hasattr(message, "response_metadata"):
                            self.response_metadata = message.response_metadata
                            logger.info("response_metadata 类型: " + str(type(self.response_metadata)))
                            logger.info("response_metadata 内容:")
                            logger.info(json.dumps(self.response_metadata, ensure_ascii=False, indent=2, default=str))
                        
                        # 检查所有属性
                        logger.info("=" * 80)
                        logger.info("message 对象的所有属性:")
                        logger.info("=" * 80)
                        for attr in dir(message):
                            if not attr.startswith("_"):
                                try:
                                    value = getattr(message, attr)
                                    if not callable(value):
                                        value_str = str(value)
                                        if len(value_str) > 500:
                                            value_str = value_str[:500] + "..."
                                        logger.info(f"  {attr}: {type(value)} = {value_str}")
                                except:
                                    pass


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


def test_response_metadata():
    """测试 response_metadata 和 llm_output 中是否包含 reasoning_content"""
    logger.info("=" * 80)
    logger.info("测试: 检查 response_metadata 和 llm_output")
    logger.info("=" * 80)
    
    config = load_env_config()
    api_key = config.get("OPENAI_API_KEY", "")
    base_url = config.get("OPENAI_BASE_URL", "")
    model = config.get("LLM_MODEL", "deepseek-r1-250528")
    
    if not api_key or not base_url:
        logger.error("缺少必要的配置：OPENAI_API_KEY 或 OPENAI_BASE_URL")
        return
    
    # 创建回调处理器
    capture_handler = ResponseCaptureHandler()
    
    try:
        # 创建 LangChain 客户端
        llm = ChatOpenAI(
            model=model,
            openai_api_key=api_key,
            base_url=base_url,
            temperature=0.7,
            max_tokens=2048,
            callbacks=[capture_handler]
        )
        
        # 调用模型
        message = HumanMessage(content="请帮我记录血压，收缩压是120，舒张压是80")
        logger.info(f"发送消息: {message.content}")
        
        response = llm.invoke([message])
        
        # 检查捕获的数据
        logger.info("=" * 80)
        logger.info("检查捕获的数据中是否包含 reasoning_content:")
        logger.info("=" * 80)
        
        # 检查 llm_output
        if capture_handler.llm_output:
            logger.info("检查 llm_output...")
            if isinstance(capture_handler.llm_output, dict):
                for key, value in capture_handler.llm_output.items():
                    if "reason" in key.lower() or "think" in key.lower():
                        logger.info(f"  ✅ 在 llm_output 中找到相关字段: {key}")
                        logger.info(f"     值: {str(value)[:500]}")
        
        # 检查 response_metadata
        if capture_handler.response_metadata:
            logger.info("检查 response_metadata...")
            if isinstance(capture_handler.response_metadata, dict):
                for key, value in capture_handler.response_metadata.items():
                    if "reason" in key.lower() or "think" in key.lower():
                        logger.info(f"  ✅ 在 response_metadata 中找到相关字段: {key}")
                        logger.info(f"     值: {str(value)[:500]}")
                    
                    # 检查是否有原始响应
                    if "raw_response" in key.lower() or "response" in key.lower():
                        logger.info(f"  找到可能的原始响应字段: {key}")
                        if isinstance(value, dict):
                            # 检查原始响应中是否有 reasoning_content
                            if "reasoning_content" in value:
                                logger.info(f"  ✅ 在原始响应中找到 reasoning_content!")
                                logger.info(f"     值: {str(value['reasoning_content'])[:500]}")
        
        # 检查 response 对象的 response_metadata
        if hasattr(response, "response_metadata"):
            metadata = response.response_metadata
            logger.info("检查 response.response_metadata...")
            if isinstance(metadata, dict):
                for key, value in metadata.items():
                    if "reason" in key.lower() or "think" in key.lower():
                        logger.info(f"  ✅ 在 response.response_metadata 中找到相关字段: {key}")
                        logger.info(f"     值: {str(value)[:500]}")
        
        logger.info("=" * 80)
        logger.info("测试完成")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"测试失败: {str(e)}", exc_info=True)


if __name__ == "__main__":
    test_response_metadata()

