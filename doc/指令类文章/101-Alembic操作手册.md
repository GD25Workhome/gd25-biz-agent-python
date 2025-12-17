# 101-Alembic 操作手册

Alembic 是 SQLAlchemy 的数据库迁移工具，用于管理数据库 schema 的版本变更。

## 一、基本操作

### 1.1 创建迁移脚本

```bash
# 自动生成迁移脚本（基于模型变更，推荐）
alembic revision --autogenerate -m "描述信息"

# 创建空迁移脚本（手动编写）
alembic revision -m "描述信息"
```

**示例：**
```bash
# 添加用户表
alembic revision --autogenerate -m "add user table"

# 修改订单表结构
alembic revision --autogenerate -m "update order table"
```

### 1.2 执行迁移

```bash
# 升级到最新版本（最常用）
alembic upgrade head

# 升级到指定版本
alembic upgrade <revision_id>

# 升级一个版本
alembic upgrade +1

# 降级一个版本
alembic downgrade -1

# 降级到指定版本
alembic downgrade <revision_id>

# 降级到基础版本
alembic downgrade base
```

**示例：**
```bash
# 升级到最新
alembic upgrade head

# 升级到特定版本
alembic upgrade abc123def456

# 回退一个版本
alembic downgrade -1
```

### 1.3 查看迁移状态

```bash
# 查看当前数据库版本
alembic current

# 查看迁移历史
alembic history

# 查看迁移历史（详细）
alembic history --verbose

# 查看特定版本的详细信息
alembic history <revision_id>
```

## 二、常用工作流程

### 2.1 开发新功能（添加表/字段）

```bash
# 1. 修改模型文件（app/models/xxx.py）
# 例如：添加新字段、新表等

# 2. 生成迁移脚本
alembic revision --autogenerate -m "add user email field"

# 3. 检查生成的迁移脚本（alembic/versions/xxx.py）
# 确认变更是否正确

# 4. 执行迁移
alembic upgrade head

# 5. 验证数据库结构
# 可以连接数据库查看表结构
```

### 2.2 回退迁移

```bash
# 1. 查看当前版本
alembic current

# 2. 查看迁移历史
alembic history

# 3. 回退到上一个版本
alembic downgrade -1

# 或回退到指定版本
alembic downgrade <revision_id>
```

### 2.3 初始化新数据库

```bash
# 1. 确保数据库配置正确（.env 文件中配置以下变量）
#    DB_HOST=localhost
#    DB_PORT=5432
#    DB_USER=postgres
#    DB_PASSWORD=your_password
#    DB_NAME=your_database_name

# 2. 确保数据库已创建
python scripts/init_db.py

# 3. 执行所有迁移
alembic upgrade head
```

**注意：**
- 项目使用 `psycopg3`（而非 `psycopg2`）作为 PostgreSQL 驱动
- 确保已安装所有依赖：`pip install -r requirements.txt`
- 数据库连接 URL 格式为：`postgresql+psycopg://user:password@host:port/dbname`

## 三、注意事项

### 3.1 迁移脚本检查

- ✅ **自动生成的脚本需要检查**：`--autogenerate` 可能无法检测所有变更
- ✅ **手动修改复杂变更**：如数据迁移、索引重命名等
- ✅ **确保降级逻辑正确**：每个 `upgrade()` 都应该有对应的 `downgrade()`

### 3.2 生产环境

- ⚠️ **执行前备份数据库**：生产环境迁移前必须备份
- ⚠️ **在测试环境先验证**：确保迁移脚本正确
- ⚠️ **避免直接修改已执行的迁移**：应创建新的迁移脚本

### 3.3 常见问题

**问题 1：迁移脚本检测不到模型变更**

**解决：**
- 确保所有模型都已导入（在 `alembic/env.py` 中导入）
- 检查模型是否继承自 `Base`
- 确认模型文件在正确的路径下

**问题 2：迁移执行失败**

**解决：**
- 查看错误信息，通常是 SQL 语法错误
- 检查数据库连接配置（`.env` 中的 `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`）
- 确认数据库用户有足够权限
- 如果出现 `No module named 'psycopg2'` 错误，确保已安装 `psycopg[binary]>=3.1.0`（项目使用 psycopg3）

**问题 3：迁移历史不一致**

**解决：**
- 使用 `alembic current` 查看当前版本
- 使用 `alembic history` 查看所有版本
- 如果版本不一致，可能需要手动修复 `alembic_version` 表

## 四、配置文件说明

### 4.1 alembic.ini

主要配置项：
- `script_location = alembic`：迁移脚本目录
- `sqlalchemy.url`：数据库连接 URL（通常从环境变量读取）

### 4.2 alembic/env.py

- 自动从 `app.config.settings` 读取数据库配置
- 自动导入所有模型（通过 `Base.metadata`）

## 五、快速参考

| 操作 | 命令 |
|------|------|
| 创建迁移（自动） | `alembic revision --autogenerate -m "描述"` |
| 创建迁移（手动） | `alembic revision -m "描述"` |
| 升级到最新 | `alembic upgrade head` |
| 降级一个版本 | `alembic downgrade -1` |
| 查看当前版本 | `alembic current` |
| 查看历史 | `alembic history` |

---

**提示：** 更多详细信息请参考 `alembic/README.md` 或 Alembic 官方文档。
