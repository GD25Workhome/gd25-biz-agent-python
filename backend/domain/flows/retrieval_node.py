"""
节点2：RAG检索节点实现
负责从向量库检索相关示例，格式化后传递给节点3
"""
import logging
from typing import Dict, List, Any
from langchain_core.messages import HumanMessage

from backend.domain.state import FlowState
from backend.infrastructure.rag.retrieval import vector_db_search
from backend.infrastructure.rag.formatter import format_retrieved_examples

logger = logging.getLogger(__name__)


def retrieval_node(state: FlowState) -> FlowState:
    """
    RAG检索节点（节点2）
    
    功能：
    1. 从state中读取节点1的输出（query_text、keywords）
    2. 执行向量库检索
    3. 格式化检索结果
    4. 将结果写入state，传递给节点3
    
    Args:
        state: 流程状态对象（FlowState）
    
    Returns:
        FlowState: 更新后的状态对象
    """
    try:
        # 1. 获取节点1的输出
        prompt_vars = state.get("edges_var", {})
        query_text = prompt_vars.get("query_text", "")
        keywords = prompt_vars.get("keywords", [])
        
        # 2. 回退到原始输入（如果query_text为空）
        if not query_text:
            history_messages = state.get("history_messages", [])
            if history_messages:
                last_message = history_messages[-1]
                if isinstance(last_message, HumanMessage):
                    query_text = last_message.content
                    logger.info(f"query_text为空，使用原始输入: {query_text[:50]}...")
        
        if not query_text:
            logger.warning("查询文本为空，返回空结果")
            # 返回空结果，但不阻塞流程
            new_state = state.copy()
            if "prompt_vars" not in new_state:
                new_state["prompt_vars"] = {}
            new_state["prompt_vars"]["retrieved_examples"] = "（暂无相关示例）"
            return new_state
        
        # 3. 向量库检索
        logger.info(f"开始向量库检索：query_text='{query_text[:50]}...', keywords={keywords}")
        retrieved_examples = vector_db_search(
            query_text=query_text,
            keywords=keywords,
            top_k=15,
            similarity_threshold=0.7,
            min_results=5
        )
        
        # 4. 格式化结果
        formatted_examples = format_retrieved_examples(retrieved_examples)
        
        # 5. 更新状态
        new_state = state.copy()
        if "prompt_vars" not in new_state:
            new_state["prompt_vars"] = {}
        
        new_state["prompt_vars"]["retrieved_examples"] = formatted_examples
        
        logger.info(f"检索完成：检索到 {len(retrieved_examples)} 个示例")
        
        return new_state
        
    except Exception as e:
        logger.error(f"RAG检索节点执行失败: {e}", exc_info=True)
        # 降级：返回空结果，不阻塞流程
        new_state = state.copy()
        if "prompt_vars" not in new_state:
            new_state["prompt_vars"] = {}
        new_state["prompt_vars"]["retrieved_examples"] = "（暂无相关示例）"
        return new_state
