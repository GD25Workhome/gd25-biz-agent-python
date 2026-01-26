"""
用户信息查询节点实现
负责查询用户的健康数据（如血压信息），并将查询结果存储到流程状态中
"""
import logging
from datetime import datetime

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
    ) -> str:
        """
        查询血压数据（返回文字格式数据）
        
        Returns:
            文字格式的血压数据字符串，如果未查到数据则返回空字符串
            
        注意：
        - 直接调用 query_blood_pressure 工具的辅助函数
        - 工具内部已处理 token_id 获取（通过 get_token_id()）
        - 工具内部已处理时间范围（默认14天）
        - 返回文字格式字符串
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
        
        # 将血压数据转换为文字格式
        text_lines = []
        for record in result:
            # 格式化时间：从 ISO 格式转换为 "年月日 时分" 格式
            time_str = ""
            if record.get("record_time"):
                try:
                    # 解析 ISO 格式时间字符串
                    dt = datetime.fromisoformat(record["record_time"].replace('Z', '+00:00'))
                    # 格式化为 "年月日 时分" 格式，如 "20210126 10:00"
                    time_str = dt.strftime("%Y%m%d %H:%M")
                except Exception as e:
                    logger.warning(f"时间格式转换失败: {record.get('record_time')}, error: {e}")
                    time_str = record.get("record_time", "")
            
            # 格式化单条记录：记录时间：年月日 时分，舒张压/收缩压：xxmmHg/xxmmHg，心率：xxbpm
            # 如果字段值为空，则不拼接对应字段
            systolic = record.get("systolic")
            diastolic = record.get("diastolic")
            heart_rate = record.get("heart_rate")
            
            # 构建记录行，根据字段是否为空动态拼接
            parts = []
            
            # 时间部分（如果有时间）
            if time_str:
                parts.append(f"记录时间{time_str}")
            
            # 血压部分（如果收缩压和舒张压都有值）
            if systolic is not None and diastolic is not None:
                parts.append(f"舒张压/收缩压：{diastolic}mmHg/{systolic}mmHg")
            
            # 心率部分（如果有值）
            if heart_rate is not None:
                parts.append(f"心率：{heart_rate}bpm")
            
            # 如果有任何部分，则拼接成一行
            if parts:
                line = "，".join(parts) + "；"
            else:
                # 如果所有字段都为空，跳过这条记录
                continue
            
            # 每行数据前加空格
            text_lines.append(f"        {line}")
        
        # 组合成完整的文字格式数据
        if text_lines:
            text_format = "14日内查询到的血压数据：\n" + "\n".join(text_lines)
            logger.info(f"血压数据文字格式转换完成: {len(text_lines)}条记录")
            return text_format
        else:
            # 如果数据未查到，返回空字符串
            logger.info("血压数据文字格式转换完成: 无数据，返回空字符串")
            return ""
    
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
            # TODO 这里的数据格式需要md化，当前只有血压，先都放在统一的key下
            blood_pressure_text = await self._query_blood_pressure()
            # new_state["prompt_vars"]["blood_pressure_list"] = blood_pressure_data
            new_state["prompt_vars"]["other_info"] = blood_pressure_text
            
            if blood_pressure_text:
                logger.info(f"查询血压数据完成: 已获取文字格式数据")
            else:
                logger.info("查询血压数据完成: 未查询到数据")
            
            logger.info("用户信息查询完成")
            return new_state
            
        except Exception as e:
            logger.error(f"用户信息查询节点执行失败: {e}", exc_info=True)
            # 降级：返回原状态，不阻塞流程
            return state
