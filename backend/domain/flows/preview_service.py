"""
流程预览服务
负责流程图的生成和缓存管理
"""
import logging
from pathlib import Path
from typing import Optional

from backend.domain.flows.manager import FlowManager
from backend.app.config import find_project_root

logger = logging.getLogger(__name__)


class FlowPreviewService:
    """流程预览服务"""
    
    # 流程图预览图片存储目录（相对于项目根目录）
    PREVIEW_DIR_NAME = "static/flow_previews"
    
    @classmethod
    def _get_preview_dir(cls) -> Path:
        """获取预览图片存储目录"""
        project_root = find_project_root()
        preview_dir = project_root / cls.PREVIEW_DIR_NAME
        preview_dir.mkdir(parents=True, exist_ok=True)
        return preview_dir
    
    @classmethod
    def get_preview_image_path(cls, flow_name: str) -> Optional[Path]:
        """
        获取流程图预览图片路径
        
        Args:
            flow_name: 流程名称
            
        Returns:
            Path: 图片文件路径，如果不存在则返回None
        """
        preview_dir = cls._get_preview_dir()
        image_path = preview_dir / f"{flow_name}.png"
        if image_path.exists():
            return image_path
        return None
    
    @classmethod
    def generate_preview_image(cls, flow_name: str) -> Path:
        """
        生成流程图预览图片
        
        Args:
            flow_name: 流程名称
            
        Returns:
            Path: 生成的图片文件路径
            
        Raises:
            ValueError: 流程不存在或编译失败
        """
        # 检查流程定义是否存在（直接使用缓存，系统启动时已加载）
        if flow_name not in FlowManager._flow_definitions:
            raise ValueError(f"流程定义不存在: {flow_name}")
        
        # 获取或编译流程图
        try:
            graph = FlowManager.get_flow(flow_name)
        except Exception as e:
            logger.error(f"编译流程失败: {flow_name}, 错误: {e}")
            raise ValueError(f"编译流程失败: {flow_name}")
        
        # 生成流程图图片
        preview_dir = cls._get_preview_dir()
        image_path = preview_dir / f"{flow_name}.png"
        
        try:
            # 临时实现：生成一个占位图片
            # TODO: 实现真正的流程图可视化
            cls._generate_placeholder_image(image_path, flow_name)
            
            logger.info(f"成功生成流程图预览: {flow_name}")
            return image_path
        except Exception as e:
            logger.error(f"生成流程图预览失败: {flow_name}, 错误: {e}")
            raise ValueError(f"生成流程图预览失败: {flow_name}")
    
    @classmethod
    def _generate_placeholder_image(cls, image_path: Path, flow_name: str):
        """
        生成占位图片（临时实现）
        
        TODO: 替换为真正的流程图生成逻辑
        """
        try:
            # 使用PIL生成一个简单的占位图片
            from PIL import Image, ImageDraw, ImageFont
            
            img = Image.new('RGB', (800, 600), color='white')
            draw = ImageDraw.Draw(img)
            
            # 绘制标题
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
            except:
                font = ImageFont.load_default()
            
            text = f"流程图预览: {flow_name}\n(待实现真正的可视化)"
            draw.text((50, 50), text, fill='black', font=font)
            
            img.save(image_path, 'PNG')
        except ImportError:
            # 如果PIL不可用，创建一个空文件作为占位
            logger.warning(f"PIL未安装，创建空文件作为占位: {image_path}")
            image_path.touch()

