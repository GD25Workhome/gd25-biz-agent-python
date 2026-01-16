"""
测试流程扫描逻辑
验证 medical_agent_v5 是否能被正确扫描到
"""
import sys
from pathlib import Path
import yaml

# 添加项目根目录到 Python 路径
_file_path = Path(__file__).resolve()
project_root = _file_path.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

def find_project_root() -> Path:
    """查找项目根目录"""
    current = Path(__file__).resolve()
    project_root = current.parent.parent
    return project_root

def test_scan_flows():
    """测试扫描流程"""
    print("=" * 60)
    print("测试流程扫描逻辑")
    print("=" * 60)
    
    # 1. 检查流程目录
    project_root = find_project_root()
    flows_dir = project_root / "config" / "flows"
    print(f"\n1. 流程目录: {flows_dir}")
    print(f"   目录存在: {flows_dir.exists()}")
    
    # 2. 列出所有流程目录
    print("\n2. 所有流程目录:")
    if flows_dir.exists():
        for flow_dir in flows_dir.iterdir():
            if flow_dir.is_dir():
                flow_yaml = flow_dir / "flow.yaml"
                exists = flow_yaml.exists()
                print(f"   - {flow_dir.name}: flow.yaml {'存在' if exists else '不存在'}")
    
    # 3. 手动解析 medical_agent_v5 的 flow.yaml
    print("\n3. 手动解析 medical_agent_v5 的 flow.yaml:")
    medical_v5_dir = flows_dir / "medical_agent_v5"
    medical_v5_yaml = medical_v5_dir / "flow.yaml"
    
    print(f"   - medical_agent_v5 目录: {medical_v5_dir}")
    print(f"   - medical_agent_v5 目录存在: {medical_v5_dir.exists()}")
    print(f"   - flow.yaml 文件: {medical_v5_yaml}")
    print(f"   - flow.yaml 文件存在: {medical_v5_yaml.exists()}")
    
    if medical_v5_yaml.exists():
        try:
            with open(medical_v5_yaml, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            print(f"   ✓ YAML 解析成功")
            print(f"   - 流程名称: {data.get('name', 'N/A')}")
            print(f"   - 版本: {data.get('version', 'N/A')}")
            print(f"   - 描述: {data.get('description', 'N/A')}")
            print(f"   - 节点数: {len(data.get('nodes', []))}")
            print(f"   - 边数: {len(data.get('edges', []))}")
        except Exception as e:
            print(f"   ✗ YAML 解析失败: {e}")
            import traceback
            traceback.print_exc()
    
    # 4. 检查 flow_loader.yaml 配置
    print("\n4. 检查 flow_loader.yaml 配置:")
    flow_loader_yaml = project_root / "config" / "flow_loader.yaml"
    print(f"   - 配置文件: {flow_loader_yaml}")
    print(f"   - 配置文件存在: {flow_loader_yaml.exists()}")
    
    if flow_loader_yaml.exists():
        try:
            with open(flow_loader_yaml, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            print(f"   ✓ 配置解析成功")
            preload = config.get("flows", {}).get("preload", [])
            lazy_load = config.get("flows", {}).get("lazy_load", [])
            print(f"   - 预加载流程: {preload}")
            print(f"   - 按需加载流程: {lazy_load}")
            
            if "medical_agent_v5" in preload:
                print(f"   ✓ medical_agent_v5 在预加载列表中")
            else:
                print(f"   ✗ medical_agent_v5 不在预加载列表中")
        except Exception as e:
            print(f"   ✗ 配置解析失败: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    test_scan_flows()