"""
用户信息查询节点实现
负责查询用户的健康数据（如血压信息），并将查询结果存储到流程状态中
"""
import logging
from typing import List, Dict, Any

from backend.domain.state import FlowState
from backend.domain.flows.nodes.base_function import BaseFunctionNode
from backend.domain.tools.blood_pressure_tool import query_blood_pressure_raw

logger = logging.getLogger(__name__)


class QueryUserInfoNode(BaseFunctionNode):
    """用户信息查询节点"""
    
    @classmethod
    def get_key(cls) -> str:
        """返回节点的唯一标识key"""
        return "query_user_info_node_func"
    
    def _has_blood_pressure_in_config(self) -> bool:
        """
        检查配置中是否包含 blood_pressure
        
        从节点实例的属性中读取配置（由 FunctionNodeCreator 在创建时存储）
        
        Returns:
            是否包含 blood_pressure 查询
        """
        # 从实例属性中读取配置
        config = getattr(self, "_config", {})
        query_list = config.get("query_list", [])
        
        if query_list:
            return "blood_pressure" in query_list
        
        # 默认配置：如果无法从配置读取，默认查询血压
        return True
    
    async def _query_blood_pressure(
        self
    ) -> List[Dict[str, Any]]:
        """
        查询血压数据（返回原始数据）
        
        Returns:
            血压记录列表（不包含 id 字段）
            
        注意：
        - 直接调用 query_blood_pressure 工具的辅助函数
        - 工具内部已处理 token_id 获取（通过 get_token_id()）
        - 工具内部已处理时间范围（默认14天）
        - 返回原始数据而不是格式化字符串
        """
        # 调用工具的辅助函数，获取原始数据
        # 不传入任何参数，使用默认的14天范围，token_id 从上下文自动获取
        records = await query_blood_pressure_raw()
        
        # 转换为字典列表（只保留必要字段，不包含 id）
        result = []
        for record in records:
            result.append({
                "systolic": record.systolic,
                "diastolic": record.diastolic,
                "heart_rate": record.heart_rate,
                "record_time": record.record_time.isoformat() if record.record_time else None,
                "notes": record.notes
            })
        
        logger.info(f"查询血压数据成功: count={len(result)}")
        return result
    
    async def execute(self, state: FlowState) -> FlowState:
        """
        执行用户信息查询节点
        
        功能：
        1. 检查配置中是否包含 blood_pressure
        2. 如果包含，调用血压查询接口（硬编码）
        3. 将查询结果存储到 state.prompt_vars 中
        
        Args:
            state: 流程状态对象
            
        Returns:
            FlowState: 更新后的状态对象
        """
        try:
            # 1. 检查配置中是否包含 blood_pressure
            if not self._has_blood_pressure_in_config():
                logger.info("配置中不包含 blood_pressure，跳过用户信息查询")
                return state
            
            # 2. 执行查询
            new_state = state.copy()
            if "prompt_vars" not in new_state:
                new_state["prompt_vars"] = {}
            
            # 3. 硬编码处理：直接调用血压查询接口
            blood_pressure_data = await self._query_blood_pressure()
            new_state["prompt_vars"]["blood_pressure_list"] = blood_pressure_data
            logger.info(f"查询血压数据完成: count={len(blood_pressure_data)}")
            
            logger.info("用户信息查询完成")
            return new_state
            
        except Exception as e:
            logger.error(f"用户信息查询节点执行失败: {e}", exc_info=True)
            # 降级：返回原状态，不阻塞流程
            return state
