"""
测试医生排班信息生成功能
"""
import sys
import random
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def generate_doctor_schedule(days: int = 14) -> List[Dict[str, Any]]:
    """
    生成医生排班信息（测试用，复制自 login.py）
    """
    schedule = []
    today = datetime.now().date()
    
    # 计算需要生成的周数（向上取整）
    weeks = (days + 6) // 7
    
    # 为每周生成休息时间安排
    rest_periods_by_week = {}
    
    for week in range(weeks):
        # 每周随机选择2天
        rest_days = random.sample(range(7), 2)
        rest_periods = []
        
        # 为这2天随机分配4个半天（每个半天随机选择上午或下午）
        for day in rest_days:
            period = random.choice(['morning', 'afternoon'])
            rest_periods.append((day, period))
        
        # 如果还有剩余的半天需要分配（确保总共4个半天）
        remaining_periods = 4 - len(rest_periods)
        for _ in range(remaining_periods):
            day = random.choice(rest_days)
            existing_periods = [p for d, p in rest_periods if d == day]
            if 'morning' not in existing_periods:
                period = 'morning'
            elif 'afternoon' not in existing_periods:
                period = 'afternoon'
            else:
                period = random.choice(['morning', 'afternoon'])
            rest_periods.append((day, period))
        
        rest_periods_by_week[week] = rest_periods
    
    # 生成每天的排班信息
    for day_offset in range(days):
        current_date = today + timedelta(days=day_offset)
        week_num = day_offset // 7
        day_in_week = day_offset % 7
        
        week_rest_periods = rest_periods_by_week.get(week_num, [])
        morning_rest = (day_in_week, 'morning') in week_rest_periods
        afternoon_rest = (day_in_week, 'afternoon') in week_rest_periods
        
        day_schedule = {
            "date": current_date.strftime("%Y-%m-%d")
        }
        
        if not morning_rest:
            day_schedule["morning"] = "8:00-12:00"
        if not afternoon_rest:
            day_schedule["afternoon"] = "14:00-18:00"
        
        schedule.append(day_schedule)
    
    return schedule


def test_generate_doctor_schedule():
    """测试生成医生排班信息"""
    print("=" * 60)
    print("测试医生排班信息生成功能")
    print("=" * 60)
    
    # 生成14天的排班
    schedule = generate_doctor_schedule(days=14)
    
    # 验证基本属性
    assert len(schedule) == 14, f"应该生成14天的排班，实际生成了{len(schedule)}天"
    print(f"✓ 成功生成 {len(schedule)} 天的排班信息")
    
    # 验证每天的数据结构
    for day_schedule in schedule:
        assert "date" in day_schedule, "每天必须包含日期字段"
        assert isinstance(day_schedule["date"], str), "日期必须是字符串格式"
        
        # 验证日期格式（YYYY-MM-DD）
        date_parts = day_schedule["date"].split("-")
        assert len(date_parts) == 3, "日期格式应为 YYYY-MM-DD"
        assert len(date_parts[0]) == 4, "年份应为4位数字"
        
        # 验证时间段（如果有的话）
        if "morning" in day_schedule:
            assert day_schedule["morning"] == "8:00-12:00", "上午时间段应为 8:00-12:00"
        if "afternoon" in day_schedule:
            assert day_schedule["afternoon"] == "14:00-18:00", "下午时间段应为 14:00-18:00"
    
    print("✓ 所有排班数据结构验证通过")
    
    # 验证每周休息时间（每周应该有4个半天休息）
    from datetime import datetime, timedelta
    today = datetime.now().date()
    
    weeks = (14 + 6) // 7
    for week in range(weeks):
        week_rest_count = 0
        week_days = []
        for day_offset in range(week * 7, min((week + 1) * 7, 14)):
            day_schedule = schedule[day_offset]
            week_days.append(day_schedule)
            if "morning" not in day_schedule:
                week_rest_count += 1
            if "afternoon" not in day_schedule:
                week_rest_count += 1
        
        # 打印详细信息以便调试
        if week_rest_count != 4:
            print(f"\n第{week + 1}周详细信息（应该有4个半天休息，实际有{week_rest_count}个）：")
            for day in week_days:
                print(f"  {day['date']}: ", end="")
                if "morning" in day:
                    print("上午✓ ", end="")
                else:
                    print("上午✗ ", end="")
                if "afternoon" in day:
                    print("下午✓")
                else:
                    print("下午✗")
        
        assert week_rest_count == 4, f"第{week + 1}周应该有4个半天休息，实际有{week_rest_count}个"
        print(f"✓ 第{week + 1}周休息时间验证通过（{week_rest_count}个半天）")
    
    # 打印前3天的排班信息作为示例
    print("\n" + "=" * 60)
    print("前3天排班信息示例：")
    print("=" * 60)
    for i, day_schedule in enumerate(schedule[:3]):
        print(f"\n第{i + 1}天 ({day_schedule['date']}):")
        if "morning" in day_schedule:
            print(f"  上午: {day_schedule['morning']}")
        else:
            print(f"  上午: 休息")
        if "afternoon" in day_schedule:
            print(f"  下午: {day_schedule['afternoon']}")
        else:
            print(f"  下午: 休息")
    
    print("\n" + "=" * 60)
    print("所有测试通过！")
    print("=" * 60)


if __name__ == "__main__":
    test_generate_doctor_schedule()
