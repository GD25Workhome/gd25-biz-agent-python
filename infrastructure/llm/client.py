from langchain_openai import ChatOpenAI
from app.core.config import settings

def get_llm(
    model: str = None,
    temperature: float = None,
    streaming: bool = True
) -> ChatOpenAI:
    """
    获取配置好的 LLM 客户端实例。
    
    Args:
        model (str, optional): 模型名称。如果未提供，则使用配置中的默认模型。
        temperature (float, optional): 采样温度。如果未提供，则使用配置中的默认值。
        streaming (bool): 是否启用流式输出。默认为 True。
        
    Returns:
        ChatOpenAI: 配置好的 ChatOpenAI 客户端实例。
    """
    return ChatOpenAI(
        model=model or settings.LLM_MODEL,
        temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
        openai_api_key=settings.OPENAI_API_KEY,
        openai_api_base=settings.OPENAI_BASE_URL,
        streaming=streaming
    )
