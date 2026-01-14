"""
流程预览服务
负责流程图的生成和缓存管理
"""
import logging
from pathlib import Path
from typing import Optional, Dict, List

from backend.domain.flows.manager import FlowManager
from backend.domain.flows.definition import FlowDefinition, EdgeDefinition
from backend.app.config import find_project_root

logger = logging.getLogger(__name__)


class FlowPreviewService:
    """流程预览服务"""
    
    # 流程图预览图片存储目录（相对于项目根目录）
    # 注意：图片存储在 frontend/flow_previews 目录，以便通过 /static/flow_previews/ 访问
    PREVIEW_DIR_NAME = "frontend/flow_previews"
    
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
            # 获取流程定义
            flow_def = FlowManager._flow_definitions[flow_name]
            
            # 生成真正的流程图
            cls._generate_flow_diagram(image_path, flow_def)
            
            logger.info(f"成功生成流程图预览: {flow_name}")
            return image_path
        except Exception as e:
            logger.error(f"生成流程图预览失败: {flow_name}, 错误: {e}", exc_info=True)
            raise ValueError(f"生成流程图预览失败: {flow_name}")
    
    @classmethod
    def _generate_flow_diagram(cls, image_path: Path, flow_def: FlowDefinition):
        """
        生成流程图
        
        使用 graphviz 或 matplotlib 生成真正的流程图
        
        Args:
            image_path: 图片保存路径
            flow_def: 流程定义
        """
        # 优先尝试使用 graphviz（更专业）
        try:
            cls._generate_with_graphviz(image_path, flow_def)
            return
        except ImportError:
            logger.debug("graphviz 未安装，尝试使用 matplotlib")
        except Exception as e:
            logger.warning(f"使用 graphviz 生成流程图失败: {e}，尝试使用 matplotlib")
        
        # 如果 graphviz 不可用，使用 matplotlib
        try:
            cls._generate_with_matplotlib(image_path, flow_def)
            return
        except ImportError:
            logger.warning("matplotlib 未安装，生成占位图片")
            cls._generate_placeholder_image(image_path, flow_def.name)
        except Exception as e:
            logger.error(f"使用 matplotlib 生成流程图失败: {e}，生成占位图片")
            cls._generate_placeholder_image(image_path, flow_def.name)
    
    @classmethod
    def _generate_with_graphviz(cls, image_path: Path, flow_def: FlowDefinition):
        """
        使用 graphviz 生成流程图
        
        Args:
            image_path: 图片保存路径
            flow_def: 流程定义
        """
        try:
            import graphviz
        except ImportError:
            raise ImportError("graphviz 未安装，请运行: pip install graphviz")
        
        # 创建有向图
        dot = graphviz.Digraph(
            name=flow_def.name,
            format='png',
            graph_attr={
                'rankdir': 'LR',  # 从左到右布局
                'nodesep': '1.0',
                'ranksep': '1.5',
                'fontname': 'Arial',
                'fontsize': '12'
            },
            node_attr={
                'shape': 'box',
                'style': 'rounded,filled',
                'fillcolor': '#E8F4F8',
                'fontname': 'Arial',
                'fontsize': '10'
            },
            edge_attr={
                'fontname': 'Arial',
                'fontsize': '9'
            }
        )
        
        # 添加节点
        entry_node = flow_def.entry_node
        for node in flow_def.nodes:
            node_name = node.name
            node_label = f"{node_name}\n({node.type})"
            
            # 入口节点使用不同的样式
            if node_name == entry_node:
                dot.node(
                    node_name,
                    node_label,
                    fillcolor='#FFE6CC',  # 橙色表示入口节点
                    style='rounded,filled,bold'
                )
            else:
                dot.node(node_name, node_label)
        
        # 添加 END 节点
        dot.node('END', 'END', shape='doublecircle', fillcolor='#F0F0F0', style='filled')
        
        # 按源节点分组边
        edges_by_from: Dict[str, List[EdgeDefinition]] = {}
        for edge in flow_def.edges:
            if edge.from_node not in edges_by_from:
                edges_by_from[edge.from_node] = []
            edges_by_from[edge.from_node].append(edge)
        
        # 添加边
        for from_node, edges in edges_by_from.items():
            # 检查是否有条件边（非always的边）
            conditional_edges = [e for e in edges if e.condition != "always"]
            always_edges = [e for e in edges if e.condition == "always"]
            
            if conditional_edges:
                # 条件边：为每条条件边添加标签
                for edge in conditional_edges:
                    to_node = edge.to_node if edge.to_node != "END" else "END"
                    # 简化条件表达式用于显示
                    condition_label = cls._simplify_condition_label(edge.condition)
                    dot.edge(
                        from_node,
                        to_node,
                        label=condition_label,
                        color='blue',
                        style='dashed'  # 条件边使用虚线
                    )
            
            # 普通边（always）
            for edge in always_edges:
                to_node = edge.to_node if edge.to_node != "END" else "END"
                dot.edge(
                    from_node,
                    to_node,
                    label='always',
                    color='black',
                    style='solid'  # 普通边使用实线
                )
        
        # 渲染图片
        # graphviz 的 render 方法会生成 {filename}.{format} 文件
        # 我们需要确保生成的文件名与目标文件名一致
        output_path = dot.render(
            filename=image_path.stem,
            directory=str(image_path.parent),
            format='png',
            cleanup=True  # 删除中间文件（.gv 源文件）
        )
        
        # graphviz 生成的文件可能包含完整路径，确保文件名正确
        generated_path = Path(output_path)
        if generated_path != image_path:
            # 如果生成的文件名与目标不一致，重命名
            if generated_path.exists():
                generated_path.rename(image_path)
        
        logger.debug(f"使用 graphviz 成功生成流程图: {image_path}")
    
    @classmethod
    def _generate_with_matplotlib(cls, image_path: Path, flow_def: FlowDefinition):
        """
        使用 matplotlib 生成流程图（备用方案）
        
        Args:
            image_path: 图片保存路径
            flow_def: 流程定义
        """
        try:
            import matplotlib.pyplot as plt
            import matplotlib.patches as mpatches
            from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
        except ImportError:
            raise ImportError("matplotlib 未安装，请运行: pip install matplotlib")
        
        # 创建图形
        fig, ax = plt.subplots(figsize=(16, 10))
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 10)
        ax.axis('off')
        
        # 简单的布局：将节点排列成网格
        nodes = {node.name: node for node in flow_def.nodes}
        node_positions = cls._calculate_node_positions(flow_def, nodes)
        
        # 绘制节点
        for node_name, (x, y) in node_positions.items():
            node = nodes[node_name]
            is_entry = node_name == flow_def.entry_node
            
            # 绘制节点框
            if is_entry:
                box = FancyBboxPatch(
                    (x - 0.4, y - 0.2), 0.8, 0.4,
                    boxstyle="round,pad=0.05",
                    facecolor='#FFE6CC',
                    edgecolor='black',
                    linewidth=2
                )
            else:
                box = FancyBboxPatch(
                    (x - 0.4, y - 0.2), 0.8, 0.4,
                    boxstyle="round,pad=0.05",
                    facecolor='#E8F4F8',
                    edgecolor='black',
                    linewidth=1
                )
            ax.add_patch(box)
            
            # 添加节点文本
            label = f"{node_name}\n({node.type})"
            ax.text(x, y, label, ha='center', va='center', fontsize=9, weight='bold' if is_entry else 'normal')
        
        # 绘制 END 节点
        end_pos = (9, 5)
        circle = plt.Circle(end_pos, 0.3, color='#F0F0F0', ec='black', linewidth=1)
        ax.add_patch(circle)
        ax.text(end_pos[0], end_pos[1], 'END', ha='center', va='center', fontsize=9)
        
        # 绘制边
        for edge in flow_def.edges:
            from_pos = node_positions.get(edge.from_node)
            if not from_pos:
                continue
            
            to_node = edge.to_node if edge.to_node != "END" else "END"
            to_pos = node_positions.get(to_node, end_pos)
            
            # 判断边的类型
            is_conditional = edge.condition != "always"
            
            # 绘制箭头
            arrow = FancyArrowPatch(
                from_pos,
                to_pos,
                arrowstyle='->',
                connectionstyle='arc3,rad=0.1',
                color='blue' if is_conditional else 'black',
                linestyle='--' if is_conditional else '-',
                linewidth=1.5,
                alpha=0.7
            )
            ax.add_patch(arrow)
            
            # 添加条件标签（简化）
            if is_conditional:
                mid_x = (from_pos[0] + to_pos[0]) / 2
                mid_y = (from_pos[1] + to_pos[1]) / 2
                condition_label = cls._simplify_condition_label(edge.condition)
                ax.text(mid_x, mid_y + 0.1, condition_label, ha='center', fontsize=7, 
                       bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
        
        # 添加标题
        title = f"{flow_def.name} (v{flow_def.version})"
        if flow_def.description:
            title += f"\n{flow_def.description}"
        ax.text(5, 9.5, title, ha='center', va='top', fontsize=12, weight='bold')
        
        # 保存图片
        plt.tight_layout()
        plt.savefig(image_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        
        logger.debug(f"使用 matplotlib 成功生成流程图: {image_path}")
    
    @classmethod
    def _calculate_node_positions(cls, flow_def: FlowDefinition, nodes: Dict) -> Dict[str, tuple]:
        """
        计算节点的位置（简单的网格布局）
        
        Args:
            flow_def: 流程定义
            nodes: 节点字典
            
        Returns:
            Dict[str, tuple]: 节点名称到位置的映射
        """
        positions = {}
        
        # 简单的布局策略：按入口节点开始，使用层次布局
        # 这里使用简单的网格布局作为示例
        node_list = list(nodes.keys())
        entry_node = flow_def.entry_node
        
        # 将入口节点放在第一个位置
        if entry_node in node_list:
            node_list.remove(entry_node)
            node_list.insert(0, entry_node)
        
        # 简单的网格布局
        cols = 3
        for i, node_name in enumerate(node_list):
            row = i // cols
            col = i % cols
            x = 1 + col * 3
            y = 8 - row * 2
            positions[node_name] = (x, y)
        
        return positions
    
    @classmethod
    def _simplify_condition_label(cls, condition: str) -> str:
        """
        简化条件表达式用于显示
        
        Args:
            condition: 条件表达式
            
        Returns:
            str: 简化后的标签
        """
        # 如果条件太长，截断
        if len(condition) > 30:
            return condition[:27] + "..."
        return condition
    
    @classmethod
    def _generate_placeholder_image(cls, image_path: Path, flow_name: str):
        """
        生成占位图片（备用方案）
        
        Args:
            image_path: 图片保存路径
            flow_name: 流程名称
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
            
            text = f"流程图预览: {flow_name}\n(需要安装 graphviz 或 matplotlib 以生成真正的流程图)"
            draw.text((50, 50), text, fill='black', font=font)
            
            img.save(image_path, 'PNG')
        except ImportError:
            # 如果PIL不可用，创建一个空文件作为占位
            logger.warning(f"PIL未安装，创建空文件作为占位: {image_path}")
            image_path.touch()

