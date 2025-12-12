from typing import List, Optional
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from infrastructure.database.connection import get_db
from infrastructure.database.repository import BloodPressureRepository, UserRepository

@tool
async def add_blood_pressure(
    systolic: int, 
    diastolic: int, 
    heart_rate: int, 
    config: RunnableConfig
) -> str:
    """
    记录用户的血压和心率数据。
    
    Args:
        systolic (int): 收缩压 (高压), 单位 mmHg。
        diastolic (int): 舒张压 (低压), 单位 mmHg。
        heart_rate (int): 心率, 单位 bpm。
        config (RunnableConfig): LangChain 运行时配置，包含用户信息。
        
    Returns:
        str: 操作结果的描述信息。
    """
    # 从 config 中获取 user_id (假设在 invoke graph 时传入了 configurable)
    # 这里的 configurable 结构由我们自己定义，通常在 Graph 入口处设置
    configuration = config.get("configurable", {})
    username = configuration.get("username", "guest")
    
    async for session in get_db():
        user_repo = UserRepository(session)
        bp_repo = BloodPressureRepository(session)
        
        user = await user_repo.get_or_create(username)
        record = await bp_repo.add_record(user.id, systolic, diastolic, heart_rate)
        
        return f"已成功记录: 血压 {record.systolic}/{record.diastolic} mmHg, 心率 {record.heart_rate} bpm (时间: {record.measured_at.strftime('%Y-%m-%d %H:%M')})"

@tool
async def query_blood_pressure_history(
    limit: int = 5,
    config: RunnableConfig = None
) -> str:
    """
    查询用户最近的血压历史记录。
    
    Args:
        limit (int): 返回的记录数量，默认为 5 条。
        config (RunnableConfig): LangChain 运行时配置，包含用户信息。
        
    Returns:
        str: 格式化后的历史记录文本。
    """
    configuration = config.get("configurable", {}) if config else {}
    username = configuration.get("username", "guest")
    
    async for session in get_db():
        user_repo = UserRepository(session)
        bp_repo = BloodPressureRepository(session)
        
        user = await user_repo.get_by_username(username)
        if not user:
            return "未找到该用户的记录。"
            
        records = await bp_repo.get_history(user.id, limit)
        if not records:
            return "暂无血压记录。"
            
        result = [f"最近 {len(records)} 条记录:"]
        for r in records:
            result.append(f"- {r.measured_at.strftime('%Y-%m-%d %H:%M')}: 血压 {r.systolic}/{r.diastolic}, 心率 {r.heart_rate}")
            
        return "\n".join(result)
