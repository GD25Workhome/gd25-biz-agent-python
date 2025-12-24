"""
工具注册表
统一管理所有业务工具
"""
from typing import Dict
from langchain_core.tools import BaseTool

# 工具注册表（延迟导入，避免循环依赖）
TOOL_REGISTRY: Dict[str, BaseTool] = {}


def register_tool(name: str, tool: BaseTool):
    """
    注册新工具
    
    Args:
        name: 工具名称
        tool: 工具实例
    """
    TOOL_REGISTRY[name] = tool


def get_tool(name: str) -> BaseTool:
    """
    获取工具
    
    Args:
        name: 工具名称
        
    Returns:
        工具实例
        
    Raises:
        ValueError: 工具不存在
    """
    if name not in TOOL_REGISTRY:
        raise ValueError(f"工具不存在: {name}")
    return TOOL_REGISTRY[name]


def init_tools():
    """
    初始化工具注册表
    导入所有工具并注册
    """
    # 导入血压记录工具
    from domain.tools.blood_pressure.record import record_blood_pressure
    from domain.tools.blood_pressure.query import query_blood_pressure
    from domain.tools.blood_pressure.update import update_blood_pressure
    
    # 导入复诊管理工具
    from domain.tools.appointment.create import create_appointment
    from domain.tools.appointment.query import query_appointment
    from domain.tools.appointment.update import update_appointment
    
    # 导入健康事件工具
    from domain.tools.health_event.record import record_health_event
    from domain.tools.health_event.query import query_health_event
    from domain.tools.health_event.update import update_health_event
    
    # 导入用药记录工具
    from domain.tools.medication.record import record_medication
    from domain.tools.medication.query import query_medication
    from domain.tools.medication.update import update_medication
    
    # 导入症状记录工具
    from domain.tools.symptom.record import record_symptom
    from domain.tools.symptom.query import query_symptom
    from domain.tools.symptom.update import update_symptom
    
    # 注册工具
    register_tool("record_blood_pressure", record_blood_pressure)
    register_tool("query_blood_pressure", query_blood_pressure)
    register_tool("update_blood_pressure", update_blood_pressure)
    register_tool("create_appointment", create_appointment)
    register_tool("query_appointment", query_appointment)
    register_tool("update_appointment", update_appointment)
    register_tool("record_health_event", record_health_event)
    register_tool("query_health_event", query_health_event)
    register_tool("update_health_event", update_health_event)
    register_tool("record_medication", record_medication)
    register_tool("query_medication", query_medication)
    register_tool("update_medication", update_medication)
    register_tool("record_symptom", record_symptom)
    register_tool("query_symptom", query_symptom)
    register_tool("update_symptom", update_symptom)

# 初始化工具注册表
init_tools()

