"""
流程相关路由
提供流程字典和预览功能
"""
import logging
from typing import List
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.domain.flows.manager import FlowManager
from backend.domain.flows.definition import FlowPreviewInfo
from backend.domain.flows.preview_service import FlowPreviewService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/flows", response_model=List[FlowPreviewInfo])
async def list_flows():
    """
    获取所有流程列表（流程字典）
    
    Returns:
        List[FlowPreviewInfo]: 流程列表，包含基本信息和预览信息
    """
    try:
        # 直接使用FlowManager的缓存数据（系统启动时已通过scan_flows()缓存）
        flow_definitions = FlowManager._flow_definitions
        
        logger.info(f"当前流程定义缓存数量: {len(flow_definitions)}")
        
        # 转换为FlowPreviewInfo列表
        preview_infos = []
        for flow_name, flow_def in flow_definitions.items():
            try:
                # 检查是否已编译（从_compiled_graphs缓存中判断）
                is_compiled = flow_name in FlowManager._compiled_graphs
                
                # 检查预览图片是否存在
                preview_image_path = None
                try:
                    image_path = FlowPreviewService.get_preview_image_path(flow_name)
                    if image_path:
                        # 返回相对于static目录的路径
                        preview_image_path = f"/static/flow_previews/{flow_name}.png"
                except Exception as e:
                    logger.warning(f"获取流程预览图片路径失败: {flow_name}, 错误: {e}")
                
                # 创建FlowPreviewInfo对象
                # 使用model_dump(by_alias=True)确保使用别名，因为EdgeDefinition使用了别名（from/to）
                flow_data = flow_def.model_dump(by_alias=True)
                preview_info = FlowPreviewInfo(
                    **flow_data,
                    is_compiled=is_compiled,
                    preview_image_path=preview_image_path
                )
                preview_infos.append(preview_info)
            except Exception as e:
                logger.error(f"处理流程 {flow_name} 时出错: {e}", exc_info=True)
                # 继续处理其他流程，不中断整个请求
                continue
        
        if not preview_infos:
            logger.warning("没有找到任何流程定义")
        
        return preview_infos
    except Exception as e:
        logger.error(f"获取流程列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取流程列表失败: {str(e)}")


@router.get("/flows/{flow_name}/preview")
async def generate_flow_preview(flow_name: str, force: bool = False):
    """
    生成或获取流程图预览图片
    
    Args:
        flow_name: 流程名称
        force: 是否强制重新生成（默认False，如果图片已存在则直接返回）
        
    Returns:
        FileResponse: 图片文件响应
    """
    try:
        # 检查流程是否存在（直接使用缓存，系统启动时已加载）
        if flow_name not in FlowManager._flow_definitions:
            raise HTTPException(status_code=404, detail=f"流程不存在: {flow_name}")
        
        # 检查图片是否已存在
        image_path = FlowPreviewService.get_preview_image_path(flow_name)
        
        # 如果不存在或强制重新生成，则生成新图片
        if not image_path or force:
            image_path = FlowPreviewService.generate_preview_image(flow_name)
        
        # 返回图片文件
        return FileResponse(
            path=str(image_path),
            media_type="image/png",
            filename=f"{flow_name}.png"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成流程图预览失败: {flow_name}, 错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成流程图预览失败: {str(e)}")

