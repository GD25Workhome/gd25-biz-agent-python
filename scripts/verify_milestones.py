import asyncio
import sys
import os
from datetime import datetime

# 将项目根目录添加到路径
sys.path.append(os.getcwd())

from infrastructure.database.connection import get_db
from infrastructure.database.repository import BloodPressureRepository, UserRepository
from infrastructure.rag.vector_store import VectorStore
from domain.agents.factory import AgentFactory
from langchain_core.messages import HumanMessage
from app.core.config import settings

async def verify_milestone_2():
    print("--- 验证里程碑 2 (血压功能) ---")
    async for session in get_db():
        print("1. 测试数据库连接和仓储...")
        user_repo = UserRepository(session)
        bp_repo = BloodPressureRepository(session)
        
        # 测试用户创建
        username = "test_user_m2"
        user = await user_repo.get_or_create(username)
        print(f"✅ 用户 '{user.username}' 已创建/获取，ID: {user.id}")
        
        # 测试血压记录创建
        record = await bp_repo.add_record(user.id, 120, 80, 75)
        print(f"✅ 血压记录已添加: {record.systolic}/{record.diastolic} (ID: {record.id})")
        
        # 测试血压查询
        history = await bp_repo.get_history(user.id)
        print(f"✅ 获取到历史记录: {len(history)} 条")
        
    print("2. 测试 Agent 工厂 (BloodPressureAgent)...")
    try:
        agent = AgentFactory.create_agent("blood_pressure_agent")
        print("✅ BloodPressureAgent 创建成功")
        
        # 这里不调用 agent 以节省 token，但图构建已验证
    except Exception as e:
        print(f"❌ Agent 创建失败: {e}")

async def verify_milestone_3():
    print("\n--- 验证里程碑 3 (RAG & 诊断功能) ---")
    async for session in get_db():
        print("1. 测试向量存储 (Embedding & Write)...")
        vector_store = VectorStore(session)
        
        docs = ["高血压（hypertension）是指以体循环动脉血压（收缩压和/或舒张压）增高为主要特征（收缩压≥140毫米汞柱，舒张压≥90毫米汞柱），可伴有心、脑、肾等器官的功能或器质性损害的临床综合征。"]
        metadatas = [{"source": "guideline_v1", "topic": "hypertension"}]
        
        try:
            count = await vector_store.add_documents(docs, metadatas)
            print(f"✅ 已向向量存储添加 {count} 个文档")
            
            # 测试搜索
            print("2. 测试向量搜索...")
            results = await vector_store.similarity_search("什么是高血压？", k=1)
            if results:
                print(f"✅ 找到搜索结果: {results[0][0].content[:20]}...")
            else:
                print("⚠️ 搜索无结果 (可能是距离阈值问题或为空)")
                
        except Exception as e:
            print(f"❌ RAG 验证失败 (可能是 Embedding API 问题): {e}")
            print("提示: 请确保 EMBEDDING_MODEL 和 API keys 已正确配置为 OpenAI 兼容端点。")

    print("3. 测试 Agent 工厂 (DiagnosisAgent)...")
    try:
        agent = AgentFactory.create_agent("diagnosis_agent")
        print("✅ DiagnosisAgent 创建成功")
    except Exception as e:
        print(f"❌ Agent 创建失败: {e}")

async def main():
    try:
        await verify_milestone_2()
        await verify_milestone_3()
    except Exception as e:
        print(f"❌ 验证脚本失败: {e}")

if __name__ == "__main__":
    asyncio.run(main())
