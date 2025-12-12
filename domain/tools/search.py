from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from infrastructure.database.connection import get_db
from infrastructure.rag.vector_store import VectorStore

@tool
async def search_knowledge_base(
    query: str,
    limit: int = 3,
    config: RunnableConfig = None
) -> str:
    """
    搜索医疗知识库以获取相关信息。
    用于查找有关疾病、治疗方法、指南等信息。
    
    Args:
        query (str): 搜索查询字符串。
        limit (int): 返回的结果数量。默认为 3。
        config (RunnableConfig): LangChain 运行时配置。
        
    Returns:
        str: 包含相关知识片段的格式化字符串。
    """
    async for session in get_db():
        vector_store = VectorStore(session)
        results = await vector_store.similarity_search(query, k=limit)
        
        if not results:
            return "未找到相关知识。"
            
        formatted_results = []
        for doc, distance in results:
            # distance 是余弦距离 (0-2)，如果需要可以转换为相似度分数
            # 距离越小越好
            formatted_results.append(f"Source: {doc.source}\nContent: {doc.content}\n")
            
        return "\n---\n".join(formatted_results)
