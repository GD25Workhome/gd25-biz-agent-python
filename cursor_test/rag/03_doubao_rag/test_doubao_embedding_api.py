"""
豆包 Embedding API 测试
使用 volcenginesdkarkruntime SDK 测试豆包 Embedding API

运行方式：
    cd cursor_test/rag/03_doubao_rag
    python test_doubao_embedding_api.py
"""
import sys
import os
from pathlib import Path
from typing import List, Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv(project_root / ".env")

# 从环境变量读取配置（优先使用 ARK_API_KEY，如果没有则使用 HS_EMBEDDING_API_KEY）
API_KEY = os.getenv("OPENAI_API_KEY")
# 模型ID可以从环境变量读取，如果没有则使用默认值
MODEL_ID = os.getenv("DOUBAO_EMBEDDING_MODEL_ID", "doubao-embedding-vision-250615")


def test_doubao_embedding_api(
    texts: List[str],
    encoding_format: str = "float"
) -> Optional[List[List[float]]]:
    """
    测试豆包 Embedding API（使用 volcenginesdkarkruntime SDK）
    
    Args:
        texts: 要向量化的文本列表
        encoding_format: 返回格式，可选 "float" 或 "base64"，默认为 "float"
    
    Returns:
        List[List[float]]: 向量列表，每个文本对应一个向量
    """
    if not API_KEY:
        raise ValueError("ARK_API_KEY 或 HS_EMBEDDING_API_KEY 环境变量未设置")
    
    try:
        from volcenginesdkarkruntime import Ark
    except ImportError:
        raise ImportError(
            "未安装 volcenginesdkarkruntime SDK，请运行: pip install volcenginesdkarkruntime"
        )
    
    # 创建客户端
    client = Ark(api_key=API_KEY)
    
    print(f"正在调用豆包 Embedding API...")
    print(f"  模型: {MODEL_ID}")
    print(f"  文本数量: {len(texts)}")
    print(f"  返回格式: {encoding_format}")
    print()
    
    try:
        # 调用 API - 使用 multimodal_embeddings API（与成功的代码保持一致）
        # 将文本列表转换为多模态格式
        input_data = [{"type": "text", "text": text} for text in texts]
        
        resp = client.multimodal_embeddings.create(
            model=MODEL_ID,
            input=input_data,
        )
        
        # 解析响应
        # resp.data 是 MultimodalEmbedding 对象，resp.data.embedding 是向量列表
        if hasattr(resp, 'data') and hasattr(resp.data, 'embedding'):
            # 对于单个输入，返回单个向量；对于多个输入，API 可能返回合并的向量或列表
            embedding = resp.data.embedding
            # 如果 embedding 是列表且长度与输入数量匹配，说明是多个向量
            # 否则是单个向量（可能是合并后的）
            if isinstance(embedding, list) and len(embedding) > 0:
                # 检查是否是嵌套列表（多个向量）
                if isinstance(embedding[0], list):
                    embeddings = embedding
                else:
                    # 单个向量，包装成列表
                    embeddings = [embedding]
            else:
                embeddings = [embedding] if embedding else []
        else:
            embeddings = []
        
        print("✓ API 调用成功")
        print(f"  返回向量数量: {len(embeddings)}")
        if embeddings:
            print(f"  向量维度: {len(embeddings[0])}")
        
        return embeddings
    
    except Exception as e:
        print(f"✗ API 调用失败: {e}")
        
        # 处理 SDK 特定的异常类型
        try:
            from volcenginesdkarkruntime._exceptions import (
                ArkNotFoundError,
                ArkUnauthorizedError,
                ArkPermissionDeniedError
            )
            
            if isinstance(e, ArkNotFoundError):
                print()
                print("  建议:")
                print("    1. 检查模型ID是否正确")
                print("    2. 确认是否已开通该模型服务")
                print("    3. 可以在 .env 文件中设置 DOUBAO_EMBEDDING_MODEL_ID 来指定模型ID")
            elif isinstance(e, (ArkUnauthorizedError, ArkPermissionDeniedError)):
                print()
                print("  建议:")
                print("    1. 检查 ARK_API_KEY 或 HS_EMBEDDING_API_KEY 是否正确")
                print("    2. 确认 API Key 是否有权限访问该模型")
        except ImportError:
            # 如果无法导入异常类型，使用字符串匹配
            error_str = str(e).lower()
            if "not found" in error_str or "404" in error_str:
                print()
                print("  建议:")
                print("    1. 检查模型ID是否正确")
                print("    2. 确认是否已开通该模型服务")
                print("    3. 可以在 .env 文件中设置 DOUBAO_EMBEDDING_MODEL_ID 来指定模型ID")
            elif "unauthorized" in error_str or "401" in error_str or "api key" in error_str:
                print()
                print("  建议:")
                print("    1. 检查 ARK_API_KEY 或 HS_EMBEDDING_API_KEY 是否正确")
                print("    2. 确认 API Key 是否有权限访问该模型")
        
        return None


def test_single_text():
    """测试单个文本"""
    print("=" * 60)
    print("测试 1: 单个文本向量化")
    print("=" * 60)
    print()
    
    text = "天很蓝"
    embeddings = test_doubao_embedding_api([text])
    
    if embeddings:
        print(f"\n文本: {text}")
        print(f"向量维度: {len(embeddings[0])}")
        print(f"向量前10维: {embeddings[0][:10]}")
        print()
    
    return embeddings


def test_multiple_texts():
    """测试多个文本"""
    print("=" * 60)
    print("测试 2: 多个文本批量向量化")
    print("=" * 60)
    print()
    
    texts = ["天很蓝", "海很深", "今天天气真好"]
    embeddings = test_doubao_embedding_api(texts)
    
    if embeddings:
        print(f"\n文本数量: {len(texts)}")
        for i, (text, embedding) in enumerate(zip(texts, embeddings), 1):
            print(f"  [{i}] 文本: {text}")
            print(f"      向量维度: {len(embedding)}")
            print(f"      向量前5维: {embedding[:5]}")
        print()
    
    return embeddings


def test_medical_texts():
    """测试医疗相关文本（结合项目实际场景）"""
    print("=" * 60)
    print("测试 3: 医疗场景文本向量化")
    print("=" * 60)
    print()
    
    # 使用项目中的实际场景文本
    texts = [
        "我今天量了血压，120/80",
        "我想记录血压，收缩压120，舒张压80",
        "血压已达标，继续加油保持"
    ]
    
    embeddings = test_doubao_embedding_api(texts)
    
    if embeddings:
        print(f"\n医疗场景文本数量: {len(texts)}")
        for i, (text, embedding) in enumerate(zip(texts, embeddings), 1):
            print(f"  [{i}] 文本: {text}")
            print(f"      向量维度: {len(embedding)}")
        print()
    
    return embeddings


def test_consistency():
    """测试一致性：相同文本应该返回相同向量"""
    print("=" * 60)
    print("测试 4: 向量一致性测试")
    print("=" * 60)
    print()
    
    text = "测试一致性"
    
    # 第一次调用
    print("第一次调用...")
    embeddings1 = test_doubao_embedding_api([text])
    
    # 第二次调用
    print("\n第二次调用...")
    embeddings2 = test_doubao_embedding_api([text])
    
    if embeddings1 and embeddings2:
        vec1 = embeddings1[0]
        vec2 = embeddings2[0]
        
        # 计算余弦相似度
        import numpy as np
        vec1_np = np.array(vec1)
        vec2_np = np.array(vec2)
        
        dot_product = np.dot(vec1_np, vec2_np)
        norm1 = np.linalg.norm(vec1_np)
        norm2 = np.linalg.norm(vec2_np)
        cosine_similarity = dot_product / (norm1 * norm2)
        
        print(f"\n文本: {text}")
        print(f"第一次向量维度: {len(vec1)}")
        print(f"第二次向量维度: {len(vec2)}")
        print(f"余弦相似度: {cosine_similarity:.6f}")
        
        if abs(cosine_similarity - 1.0) < 1e-6:
            print("✓ 向量一致性测试通过（两次调用返回相同向量）")
        else:
            print("⚠️  向量一致性测试未通过（两次调用返回不同向量）")
        print()


def main():
    """主函数"""
    print()
    print("=" * 60)
    print("豆包 Embedding API 测试（使用 volcenginesdkarkruntime SDK）")
    print("=" * 60)
    print()
    
    # 检查环境变量
    if not API_KEY:
        print("✗ 错误: ARK_API_KEY 或 HS_EMBEDDING_API_KEY 环境变量未设置")
        print("  请在 .env 文件中设置 ARK_API_KEY 或 HS_EMBEDDING_API_KEY")
        sys.exit(1)
    
    # 检查是否安装了 SDK
    try:
        import volcenginesdkarkruntime
    except ImportError:
        print("✗ 错误: 未安装 volcenginesdkarkruntime SDK")
        print("  请运行: pip install volcenginesdkarkruntime")
        sys.exit(1)
    
    print("环境变量检查:")
    ark_key = os.getenv("ARK_API_KEY")
    hs_key = os.getenv("HS_EMBEDDING_API_KEY")
    print(f"  ARK_API_KEY: {'已设置' if ark_key else '未设置'}")
    print(f"  HS_EMBEDDING_API_KEY: {'已设置' if hs_key else '未设置'}")
    print(f"  使用的 API Key: {'ARK_API_KEY' if ark_key else 'HS_EMBEDDING_API_KEY'}")
    print(f"  MODEL_ID: {MODEL_ID}")
    print()
    
    # 提示：如果模型ID不正确，可以在 .env 文件中设置 DOUBAO_EMBEDDING_MODEL_ID
    if not MODEL_ID:
        print("⚠️  警告: 未设置模型ID，请检查 DOUBAO_EMBEDDING_MODEL_ID 环境变量")
        print()
    
    try:
        # 执行测试
        test_single_text()
        # test_multiple_texts()
        # test_medical_texts()
        # test_consistency()
        
        print("=" * 60)
        print("✓ 所有测试完成")
        print("=" * 60)
        print()
    
    except Exception as e:
        print(f"\n✗ 测试过程中出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
