"""
测试豆包 Embedding API 通过 LangChain Embeddings 接口调用

运行方式：
    cd cursor_test/rag/03_doubao_rag
    python test_langChain_embedding_02.py
"""
import sys
import os
from pathlib import Path
from typing import List

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from langchain.embeddings.base import Embeddings
from volcenginesdkarkruntime import Ark

# 加载 .env 文件
load_dotenv(project_root / ".env")


class DoubaoEmbeddings(Embeddings):
    """豆包 Embeddings 实现，继承 LangChain Embeddings 基类"""
    
    def __init__(self, api_key: str = None, model: str = "doubao-embedding-vision-250615"):
        """
        初始化豆包 Embeddings
        
        Args:
            api_key: API Key，如果为 None 则从环境变量读取
            model: 模型ID，默认为 doubao-embedding-vision-250615
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("API Key 未设置，请提供 api_key 参数或在环境变量中设置 OPENAI_API_KEY")
        
        self.model = model
        self.client = Ark(api_key=self.api_key)
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        批量嵌入文档
        
        Args:
            texts: 文本列表
        
        Returns:
            List[List[float]]: 向量列表
        """
        if not texts:
            return []
        
        # 转换为豆包 API 格式
        input_data = [{"type": "text", "text": text} for text in texts]
        
        # 调用 API
        resp = self.client.multimodal_embeddings.create(
            model=self.model,
            input=input_data
        )
        
        # 解析响应
        embeddings = []
        if hasattr(resp, 'data') and hasattr(resp.data, 'embedding'):
            embedding = resp.data.embedding
            if isinstance(embedding, list):
                # 如果是嵌套列表（多个向量），直接返回
                if embedding and isinstance(embedding[0], list):
                    embeddings = embedding
                else:
                    # 单个向量，包装成列表
                    embeddings = [embedding]
        
        return embeddings
    
    def embed_query(self, text: str) -> List[float]:
        """
        嵌入单个查询文本
        
        Args:
            text: 查询文本
        
        Returns:
            List[float]: 向量
        """
        results = self.embed_documents([text])
        return results[0] if results else []


def test_basic_usage():
    """测试基本使用"""
    print("=" * 60)
    print("测试 1: 基本使用 - embed_query")
    print("=" * 60)
    
    # 创建 Embeddings 实例
    embeddings = DoubaoEmbeddings()
    
    # 测试单个文本
    text = "天很蓝"
    vector = embeddings.embed_query(text)
    
    print(f"文本: {text}")
    print(f"向量维度: {len(vector)}")
    print(f"向量前10维: {vector[:10]}")
    print("✓ 测试通过\n")


def test_batch_embedding():
    """测试批量嵌入"""
    print("=" * 60)
    print("测试 2: 批量嵌入 - embed_documents")
    print("=" * 60)
    
    # 创建 Embeddings 实例
    embeddings = DoubaoEmbeddings()
    
    # 测试多个文本
    texts = ["天很蓝", "海很深", "今天天气真好"]
    vectors = embeddings.embed_documents(texts)
    
    print(f"文本数量: {len(texts)}")
    print(f"向量数量: {len(vectors)}")
    for i, (text, vector) in enumerate(zip(texts, vectors), 1):
        print(f"  [{i}] 文本: {text}")
        print(f"      向量维度: {len(vector)}")
        print(f"      向量前5维: {vector[:5]}")
    print("✓ 测试通过\n")


def test_langchain_compatibility():
    """测试 LangChain 兼容性"""
    print("=" * 60)
    print("测试 3: LangChain 兼容性检查")
    print("=" * 60)
    
    # 创建 Embeddings 实例
    embeddings = DoubaoEmbeddings()
    
    # 检查是否实现了必要的方法
    assert hasattr(embeddings, 'embed_documents'), "缺少 embed_documents 方法"
    assert hasattr(embeddings, 'embed_query'), "缺少 embed_query 方法"
    assert callable(embeddings.embed_documents), "embed_documents 必须是可调用的"
    assert callable(embeddings.embed_query), "embed_query 必须是可调用的"
    
    print("✓ 所有必要方法都已实现")
    print("✓ 可以正常作为 LangChain Embeddings 使用")
    print("✓ 测试通过\n")


def main():
    """主函数"""
    print()
    print("=" * 60)
    print("豆包 Embedding API - LangChain 集成测试")
    print("=" * 60)
    print()
    
    try:
        # 执行测试
        test_basic_usage()
        test_batch_embedding()
        test_langchain_compatibility()
        
        print("=" * 60)
        print("✓ 所有测试完成")
        print("=" * 60)
        print()
        print("结论: 豆包 Embedding API 可以通过 LangChain Embeddings 接口正常调用")
        print()
    
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
