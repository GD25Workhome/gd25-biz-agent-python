# Python 模块导入路径问题解析

## 问题描述

运行 pytest 测试时出现错误：
```
ModuleNotFoundError: No module named 'infrastructure'
```

## 问题原理

### 1. Python 模块搜索机制

Python 在导入模块时，会按照以下顺序搜索：

1. **内置模块**：Python 标准库
2. **sys.path**：包含以下路径的列表：
   - 当前脚本所在目录（`sys.path[0]`）
   - `PYTHONPATH` 环境变量指定的目录
   - Python 安装目录
   - site-packages 目录

### 2. pytest 的路径处理机制

当运行 pytest 时：

```bash
pytest cursor_test/M1_test/infrastructure/test_database_models.py
```

pytest 会：
1. 将**测试文件所在的目录**添加到 `sys.path[0]`
   - 即：`/path/to/project/cursor_test/M1_test/infrastructure/`
2. 将**项目根目录**（pytest 的 rootdir）添加到 `sys.path`
   - 但这是在 pytest 内部，对于 `conftest.py` 的导入可能不够

### 3. 问题根源

在 `conftest.py` 中：
```python
from infrastructure.database.base import Base
```

当 pytest 加载 `conftest.py` 时：
- `conftest.py` 位于：`cursor_test/M1_test/conftest.py`
- pytest 可能将 `cursor_test/M1_test/` 添加到路径
- 但 `infrastructure` 模块在项目根目录：`/path/to/project/infrastructure/`
- **项目根目录不在 `sys.path` 中**，导致找不到模块

### 4. 目录结构示意

```
项目根目录/
├── infrastructure/          # 需要导入的模块
│   └── database/
│       └── base.py
├── cursor_test/
│   └── M1_test/
│       ├── conftest.py     # 在这里导入 infrastructure
│       └── infrastructure/
│           └── test_database_models.py
```

## 解决方案

### 方案 1：在 conftest.py 中添加路径（推荐）

在 `conftest.py` 文件开头添加：

```python
import sys
from pathlib import Path

# 将项目根目录添加到 Python 路径
# conftest.py 位于: cursor_test/M1_test/conftest.py
# 项目根目录: cursor_test/M1_test/../../
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 然后才能导入项目模块
from infrastructure.database.base import Base
```

**优点**：
- 不依赖运行目录
- 自动找到项目根目录
- 适用于所有测试文件

### 方案 2：使用 pytest.ini 配置

创建 `pytest.ini` 文件：

```ini
[pytest]
pythonpath = .
```

**优点**：
- 配置简单
- 全局生效

**缺点**：
- 需要额外配置文件
- 路径是相对于 `pytest.ini` 所在目录

### 方案 3：从项目根目录运行 pytest

```bash
# 确保在项目根目录
cd /path/to/project
pytest cursor_test/M1_test/
```

**优点**：
- 简单直接

**缺点**：
- 依赖运行目录
- 不够灵活

## 最佳实践

### 1. 使用 Path 对象动态获取路径

```python
from pathlib import Path

# 获取 conftest.py 的绝对路径
conftest_path = Path(__file__).resolve()
# 计算项目根目录（向上两级）
project_root = conftest_path.parent.parent.parent
```

### 2. 检查路径是否已存在

```python
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
```

避免重复添加路径。

### 3. 使用 insert(0, ...) 而不是 append()

`insert(0, ...)` 将路径添加到列表开头，优先级最高。

## 验证方法

### 1. 检查 sys.path

```python
import sys
print('\n'.join(sys.path))
```

### 2. 测试导入

```python
try:
    from infrastructure.database.base import Base
    print("✓ 导入成功")
except ImportError as e:
    print(f"✗ 导入失败: {e}")
```

### 3. 运行测试

```bash
# 从任意目录运行都应该成功
cd /any/directory
pytest /path/to/project/cursor_test/M1_test/
```

## 相关概念

### sys.path 的组成

```python
import sys
print(sys.path)
# 输出示例：
# [
#   '/path/to/project/cursor_test/M1_test/infrastructure',  # 当前脚本目录
#   '/path/to/project',                                      # 项目根目录（我们添加的）
#   '/usr/lib/python3.9',                                    # Python 标准库
#   '/usr/lib/python3.9/site-packages',                      # 第三方包
# ]
```

### Python 模块导入顺序

1. 检查是否为内置模块
2. 检查 `sys.path` 中的每个目录
3. 找到第一个匹配的模块就停止搜索
4. 如果都找不到，抛出 `ModuleNotFoundError`

## 总结

**问题本质**：pytest 将测试文件所在目录添加到 `sys.path`，而不是项目根目录，导致无法导入项目模块。

**解决方法**：在 `conftest.py` 中动态添加项目根目录到 `sys.path`，确保无论从哪个目录运行测试都能找到项目模块。

**关键代码**：
```python
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
```

这样就能确保测试代码可以正确导入项目模块了！

