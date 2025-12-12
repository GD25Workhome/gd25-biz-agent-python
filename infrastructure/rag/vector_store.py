from typing import List, Dict, Any, Tuple
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from infrastructure.database.models import KnowledgeBase
from infrastructure.rag.embeddings import get_embeddings
from infrastructure.database.connection import get_db

class VectorStore:
    """
    向量存储类 (Vector Store)
    
    封装了基于 PostgreSQL pgvector 的向量存储和检索逻辑。
    """
    
    def __init__(self, session: AsyncSession):
        """
        初始化 VectorStore。
        
        Args:
            session (AsyncSession): 数据库会话。
        """
        self.session = session
        self.embeddings = get_embeddings()

    async def add_documents(self, documents: List[str], metadatas: List[Dict[str, Any]] = None):
        """
        添加文档到向量库。
        
        该方法会自动调用 Embedding 模型生成向量，并存入数据库。
        
        Args:
            documents (List[str]): 文档内容列表。
            metadatas (List[Dict[str, Any]]): 对应的元数据列表 (可选)。
            
        Returns:
            int: 成功添加的文档数量。
        """
        if metadatas is None:
            metadatas = [{}] * len(documents)
        
        # 批量生成 Embedding 向量
        vectors = await self.embeddings.aembed_documents(documents)
        
        new_entries = []
        for doc, meta, vector in zip(documents, metadatas, vectors):
            entry = KnowledgeBase(
                content=doc,
                embedding=vector,
                metadata_json=meta,
                source=meta.get("source", "unknown")
            )
            new_entries.append(entry)
        
        self.session.add_all(new_entries)
        await self.session.commit()
        return len(new_entries)

    async def similarity_search(self, query: str, k: int = 4) -> List[Tuple[KnowledgeBase, float]]:
        """
        执行相似度搜索 (基于余弦距离)。
        
        Args:
            query (str): 查询文本。
            k (int): 返回结果数量。
            
        Returns:
            List[Tuple[KnowledgeBase, float]]: 包含 (文档对象, 距离值) 的元组列表。
            注意: 距离值越小表示越相似 (0=完全相同, 1=正交, 2=完全相反)。
        """
        query_vector = await self.embeddings.aembed_query(query)
        
        # 使用 pgvector 的余弦距离操作符 (<=>)
        # 排序: 距离越小越好 (ASC)
        stmt = (
            select(KnowledgeBase, KnowledgeBase.embedding.cosine_distance(query_vector).label("distance"))
            .order_by(KnowledgeBase.embedding.cosine_distance(query_vector))
            .limit(k)
        )
        
        result = await self.session.execute(stmt)
        return result.all()
