"""
数据库SQL日志功能测试

测试SQLAlchemy事件监听器的SQL日志记录功能
"""
import asyncio
import logging
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.core.config import settings
from infrastructure.database.connection import get_async_engine, get_async_session_factory
from infrastructure.database.repository.blood_pressure_repository import BloodPressureRepository
from infrastructure.database.models.blood_pressure import BloodPressureRecord


# 配置日志格式，便于查看SQL日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


async def test_sql_logging():
    """
    测试SQL日志功能
    
    测试场景：
    1. 创建记录（INSERT）
    2. 查询记录（SELECT）
    3. 更新记录（UPDATE）
    4. 删除记录（DELETE）
    """
    print("=" * 60)
    print("开始测试SQL日志功能")
    print("=" * 60)
    
    # 检查是否启用了SQL日志
    if not settings.DB_SQL_LOG_ENABLED:
        print("⚠️  警告：DB_SQL_LOG_ENABLED 未启用，请在 .env 文件中设置 DB_SQL_LOG_ENABLED=true")
        print("   当前配置：")
        print(f"   - DB_SQL_LOG_ENABLED: {settings.DB_SQL_LOG_ENABLED}")
        print(f"   - DB_SQL_LOG_LEVEL: {settings.DB_SQL_LOG_LEVEL}")
        print(f"   - DB_SQL_LOG_SLOW_QUERY_THRESHOLD: {settings.DB_SQL_LOG_SLOW_QUERY_THRESHOLD}")
        print(f"   - DB_SQL_LOG_INCLUDE_PARAMS: {settings.DB_SQL_LOG_INCLUDE_PARAMS}")
        return
    
    print(f"✅ SQL日志已启用")
    print(f"   - 日志级别: {settings.DB_SQL_LOG_LEVEL}")
    print(f"   - 慢查询阈值: {settings.DB_SQL_LOG_SLOW_QUERY_THRESHOLD}秒")
    print(f"   - 记录参数: {settings.DB_SQL_LOG_INCLUDE_PARAMS}")
    print()
    
    # 获取数据库会话
    session_factory = get_async_session_factory()
    
    async with session_factory() as session:
        repo = BloodPressureRepository(session)
        
        # 测试1：创建记录（INSERT）
        print("测试1: 创建记录（INSERT）")
        print("-" * 60)
        test_user_id = "test_user_sql_logging"
        record = await repo.create(
            user_id=test_user_id,
            systolic=120,
            diastolic=80,
            heart_rate=70,
            notes="SQL日志测试记录"
        )
        await session.commit()
        print(f"✅ 创建记录成功，ID: {record.id}")
        print()
        
        # 测试2：查询记录（SELECT）
        print("测试2: 查询记录（SELECT）")
        print("-" * 60)
        records = await repo.get_by_user_id(test_user_id, limit=10)
        print(f"✅ 查询成功，找到 {len(records)} 条记录")
        print()
        
        # 测试3：更新记录（UPDATE）
        print("测试3: 更新记录（UPDATE）")
        print("-" * 60)
        if records:
            updated_record = await repo.update(
                records[0].id,
                systolic=130,
                notes="已更新"
            )
            await session.commit()
            print(f"✅ 更新记录成功，ID: {updated_record.id}")
        print()
        
        # 测试4：删除记录（DELETE）
        print("测试4: 删除记录（DELETE）")
        print("-" * 60)
        if records:
            deleted = await repo.delete(records[0].id)
            await session.commit()
            if deleted:
                print(f"✅ 删除记录成功")
            else:
                print(f"❌ 删除记录失败")
        print()
    
    print("=" * 60)
    print("测试完成！")
    print("=" * 60)
    print()
    print("请查看上方的日志输出，应该能看到以下类型的日志：")
    print("  - DEBUG级别: SQL执行前的详细信息（包括SQL语句和参数）")
    print("  - INFO级别: SQL执行成功的信息（包括执行时间）")
    print("  - WARNING级别: 慢查询警告（如果执行时间超过阈值）")
    print("  - ERROR级别: SQL执行错误（如果有错误）")


if __name__ == "__main__":
    asyncio.run(test_sql_logging())

