#!/usr/bin/env python
"""
分析血压会话响应模式

分析Excel中"新会话响应"列的回答套路，提取响应文本的组织流程
"""
import sys
import os
from pathlib import Path
import pandas as pd
import re
from typing import Dict, List, Any, Optional
from collections import defaultdict

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def extract_patient_features(row: pd.Series) -> Dict[str, Any]:
    """提取患者特征信息"""
    features = {
        "年龄": str(row.get("年龄", "")).strip() if pd.notna(row.get("年龄")) else None,
        "疾病": str(row.get("疾病", "")).strip() if pd.notna(row.get("疾病")) else None,
        "血压": str(row.get("血压", "")).strip() if pd.notna(row.get("血压")) else None,
        "症状": str(row.get("症状", "")).strip() if pd.notna(row.get("症状")) else None,
        "用药": str(row.get("用药", "")).strip() if pd.notna(row.get("用药")) else None,
        "用药情况": str(row.get("用药情况", "")).strip() if pd.notna(row.get("用药情况")) else None,
        "习惯": str(row.get("习惯", "")).strip() if pd.notna(row.get("习惯")) else None,
    }
    # 过滤掉"无"和空值
    return {k: v for k, v in features.items() if v and v != "无" and v != "nan"}


def extract_blood_pressure_from_session(session_text: str) -> Optional[Dict[str, int]]:
    """从新会话文本中提取血压值"""
    if not session_text or pd.isna(session_text):
        return None
    
    # 匹配模式：高压/收缩压/高，低压/舒张压/低，脉搏
    bp_patterns = [
        r"高压[：:]?\s*(\d+)|收缩压[：:]?\s*(\d+)|高[：:]?\s*(\d+)",
        r"低压[：:]?\s*(\d+)|舒张压[：:]?\s*(\d+)|低[：:]?\s*(\d+)",
        r"脉搏[：:]?\s*(\d+)|心率[：:]?\s*(\d+)",
    ]
    
    result = {}
    matches = []
    for pattern in bp_patterns:
        match = re.search(pattern, session_text, re.IGNORECASE)
        if match:
            value = int(match.group(1) or match.group(2) or match.group(3) or match.group(4))
            if "高压" in pattern or "收缩压" in pattern or "高[：:]" in pattern:
                result["收缩压"] = value
            elif "低压" in pattern or "舒张压" in pattern or "低[：:]" in pattern:
                result["舒张压"] = value
            elif "脉搏" in pattern or "心率" in pattern:
                result["脉搏"] = value
    
    return result if result else None


def parse_response_structure(response_text: str, bp_status: str = None) -> Dict[str, Any]:
    """解析响应文本的结构
    
    Args:
        response_text: 响应文本
        bp_status: 血压列的值（如"单次血压记录中度偏高"），用于辅助判断评价级别
    """
    if not response_text or pd.isna(response_text):
        return {}
    
    structure = {
        "正向反馈": False,
        "血压记录确认": False,
        "血压评价": False,
        "血压评价级别": None,  # 达标/轻度偏高/中度偏高/重度偏高/低压偏低/高压偏低
        "症状说明": False,
        "预警信息": False,
        "预警类型": None,  # 血压预警/症状预警/脉搏预警
        "就医引导": False,
        "门诊排班": False,
        "生活方式建议": False,
        "监测建议": False,
        "文章推送": False,
        "文章数量": 0,
        "趋势分析": False,
        "对比分析": False,
    }
    
    text = str(response_text)
    
    # 1. 正向反馈和记录确认
    if any(phrase in text for phrase in ["习惯非常棒", "主动监测", "帮你记录", "记录了这次", "记录了今天", "记录下今天", "保存了今天"]):
        structure["正向反馈"] = True
        structure["血压记录确认"] = True
    
    # 2. 血压评价
    # 优先从bp_status中提取，如果没有则从响应文本中提取
    bp_eval_level = None
    if bp_status and pd.notna(bp_status):
        bp_status_str = str(bp_status)
        if "达标" in bp_status_str:
            bp_eval_level = "达标"
        elif "重度偏高" in bp_status_str:
            bp_eval_level = "重度偏高"
        elif "中度偏高" in bp_status_str:
            bp_eval_level = "中度偏高"
        elif "轻度偏高" in bp_status_str:
            bp_eval_level = "轻度偏高"
        elif "高压偏低" in bp_status_str:
            bp_eval_level = "高压偏低"
        elif "低压偏低" in bp_status_str:
            bp_eval_level = "低压偏低"
    
    # 如果从bp_status没找到，再从文本中提取
    if not bp_eval_level:
        bp_eval_patterns = {
            "达标": [r"达标", r"正常范围", r"在目标范围内", r"正常高值范围", r"整体情况良好"],
            "轻度偏高": [r"轻度偏高", r"略高", r"稍微偏高"],
            "中度偏高": [r"中度偏高", r"明显高于正常范围", r"需要关注"],
            "重度偏高": [r"重度偏高", r">=180", r">=110", r"需要紧急", r"尽快就医", r"比较严重"],
            "低压偏低": [r"低压偏低", r"舒张压.*偏低"],
            "高压偏低": [r"高压偏低", r"收缩压.*偏低"],
        }
        
        for level, patterns in bp_eval_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    bp_eval_level = level
                    break
            if bp_eval_level:
                break
    
    if bp_eval_level:
        structure["血压评价"] = True
        structure["血压评价级别"] = bp_eval_level
    
    # 3. 症状说明
    if any(phrase in text for phrase in ["身体不适", "不舒服", "身体反应", "症状"]):
        structure["症状说明"] = True
    
    # 4. 预警信息
    if any(phrase in text for phrase in ["需要重视", "引起重视", "尽快就医", "尽快回院", "需要关注", "需预警"]):
        structure["预警信息"] = True
        if any(phrase in text for phrase in ["血压", "偏高", "偏低"]):
            structure["预警类型"] = "血压预警"
        elif any(phrase in text for phrase in ["症状", "不适", "胸闷", "头晕"]):
            structure["预警类型"] = "症状预警"
        elif any(phrase in text for phrase in ["脉搏", "心率"]):
            structure["预警类型"] = "脉搏预警"
    
    # 5. 就医引导和门诊排班
    if any(phrase in text for phrase in ["尽快就医", "建议你尽快", "让医生评估", "门诊排班", "出诊时间"]):
        structure["就医引导"] = True
    if "scheduleStartDay" in text or "门诊排班" in text or "出诊时间" in text:
        structure["门诊排班"] = True
    
    # 6. 生活方式建议
    if any(phrase in text for phrase in ["注意休息", "低盐饮食", "适度运动", "保持", "避免", "生活习惯"]):
        structure["生活方式建议"] = True
    
    # 7. 监测建议
    if any(phrase in text for phrase in ["继续监测", "规律监测", "坚持监测", "记录更多数据", "持续监测"]):
        structure["监测建议"] = True
    
    # 8. 文章推送
    article_count = len(re.findall(r"articleId=\d+", text))
    if article_count > 0:
        structure["文章推送"] = True
        structure["文章数量"] = article_count
    
    # 9. 趋势分析（需要历史数据）
    # 更精确的匹配，避免误判
    if any(phrase in text for phrase in ["血压趋势图", "趋势图", "变化趋势", "趋势分析", "血压变化趋势"]):
        structure["趋势分析"] = True
    
    # 10. 对比分析
    if any(phrase in text for phrase in ["相比", "上次", "之前", "对比"]):
        structure["对比分析"] = True
    
    return structure


def analyze_all_responses(excel_path: Path) -> List[Dict[str, Any]]:
    """分析所有响应"""
    excel_file = pd.ExcelFile(excel_path)
    first_sheet = excel_file.sheet_names[0]
    df = pd.read_excel(excel_path, sheet_name=first_sheet)
    
    results = []
    
    for idx, row in df.iterrows():
        # 跳过空行
        new_session = row.get("新会话")
        new_session_response = row.get("新会话响应")
        if pd.isna(new_session) or pd.isna(new_session_response):
            continue
        
        # 提取患者特征
        patient_features = extract_patient_features(row)
        
        # 从新会话中提取血压值
        bp_values = extract_blood_pressure_from_session(str(new_session))
        
        # 获取血压状态（从"血压"列）
        bp_status = str(row.get("血压", "")).strip() if pd.notna(row.get("血压")) else None
        
        # 解析响应结构
        response_structure = parse_response_structure(str(new_session_response), bp_status)
        
        # 获取ext字段（人工标注）
        ext_note = str(row.get("ext", "")).strip() if pd.notna(row.get("ext")) else ""
        
        results.append({
            "行号": idx + 2,  # Excel行号（含表头）
            "患者特征": patient_features,
            "血压值": bp_values,
            "新会话": str(new_session)[:100] + "..." if len(str(new_session)) > 100 else str(new_session),
            "响应结构": response_structure,
            "ext标注": ext_note,
            "完整响应": str(new_session_response)[:500] + "..." if len(str(new_session_response)) > 500 else str(new_session_response),
        })
    
    return results


def aggregate_patterns(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """聚合分析模式"""
    patterns = {
        "结构出现频率": defaultdict(int),
        "组合模式": defaultdict(int),
        "预警触发条件": [],
        "血压评价分布": defaultdict(int),
        "文章推送情况": {"有推送": 0, "无推送": 0, "平均数量": 0},
    }
    
    total = len(results)
    total_articles = 0
    articles_count = 0
    
    for result in results:
        structure = result["响应结构"]
        patient_features = result["患者特征"]
        
        # 统计各结构出现频率
        for key, value in structure.items():
            if isinstance(value, bool) and value:
                patterns["结构出现频率"][key] += 1
            elif isinstance(value, (int, str)) and value:
                patterns["结构出现频率"][key] += 1
        
        # 统计组合模式
        active_structures = [k for k, v in structure.items() if (isinstance(v, bool) and v) or (isinstance(v, (int, str)) and v)]
        if active_structures:
            pattern_key = " + ".join(sorted(active_structures))
            patterns["组合模式"][pattern_key] += 1
        
        # 收集预警触发条件
        if structure.get("预警信息"):
            warning_condition = {
                "疾病": patient_features.get("疾病"),
                "症状": patient_features.get("症状"),
                "血压": patient_features.get("血压"),
                "血压值": result.get("血压值"),
                "ext标注": result.get("ext标注"),
            }
            patterns["预警触发条件"].append(warning_condition)
        
        # 统计血压评价分布
        if structure.get("血压评价级别"):
            patterns["血压评价分布"][structure["血压评价级别"]] += 1
        
        # 统计文章推送
        if structure.get("文章推送"):
            patterns["文章推送情况"]["有推送"] += 1
            total_articles += structure.get("文章数量", 0)
            articles_count += 1
    
    # 计算平均文章数量
    if articles_count > 0:
        patterns["文章推送情况"]["平均数量"] = round(total_articles / articles_count, 2)
    patterns["文章推送情况"]["无推送"] = total - articles_count
    
    return patterns


def generate_analysis_report(results: List[Dict[str, Any]], patterns: Dict[str, Any], total_count: int) -> str:
    """生成分析报告"""
    report_lines = []
    
    report_lines.append("# 患者首次发言的案例分析\n")
    report_lines.append(f"## 数据概览\n")
    report_lines.append(f"- 分析sheet页：第一个sheet（患者有数据（无历史会话，无历史action））\n")
    report_lines.append(f"- 总记录数：{total_count} 条\n")
    report_lines.append(f"- 有效分析记录数：{len(results)} 条\n\n")
    
    report_lines.append("---\n\n")
    
    # 1. 响应文本组织流程
    report_lines.append("## 1. 响应文本的组织流程（全量结构）\n\n")
    
    report_lines.append("基于对所有响应文本的分析，响应文本通常按以下流程组织（按出现顺序）：\n\n")
    
    flow_steps = [
        ("正向反馈与记录确认", "正向反馈", "必需", "包含对患者主动监测的表扬和血压记录已完成的确认"),
        ("血压数据评价", "血压评价", "必需", "对本次记录的血压值进行评价（达标/轻度偏高/中度偏高/重度偏高/低压偏低/高压偏低）"),
        ("症状说明", "症状说明", "条件必需", "当患者有症状时，说明血压异常可能引起的身体不适"),
        ("预警信息提示", "预警信息", "条件必需", "当触发预警条件时，提示患者需要重视并引导就医"),
        ("就医引导", "就医引导", "条件必需", "当有预警或需要就医时，引导患者回院就医"),
        ("门诊排班信息", "门诊排班", "条件必需", "当需要就医时，提供医生门诊排班查询功能"),
        ("生活方式建议", "生活方式建议", "条件必需", "根据患者情况提供生活方式调整建议（饮食、运动、作息等）"),
        ("监测建议", "监测建议", "条件必需", "建议患者继续规律监测血压，养成监测习惯"),
        ("趋势分析", "趋势分析", "条件必需", "当有足够历史数据时，进行血压趋势分析（本sheet页无此情况）"),
        ("对比分析", "对比分析", "条件必需", "当有上次记录时，进行对比分析（本sheet页无此情况）"),
        ("健康文章推送", "文章推送", "常见", "推送相关的健康科普文章，通常3篇左右"),
    ]
    
    for step_name, key, necessity, description in flow_steps:
        frequency = patterns["结构出现频率"].get(key, 0)
        percentage = round(frequency / len(results) * 100, 1) if results else 0
        report_lines.append(f"### {step_name}\n")
        report_lines.append(f"- **必要性**：{necessity}\n")
        report_lines.append(f"- **出现频率**：{frequency} 次 ({percentage}%)\n")
        report_lines.append(f"- **说明**：{description}\n\n")
    
    report_lines.append("### 典型响应流程示例\n\n")
    report_lines.append("#### 示例1：有预警的情况（必需结构）\n")
    report_lines.append("```\n")
    report_lines.append("1. 正向反馈与记录确认\n")
    report_lines.append("2. 血压数据评价（中度/重度偏高）\n")
    report_lines.append("3. 症状说明（如有症状）\n")
    report_lines.append("4. 预警信息提示\n")
    report_lines.append("5. 就医引导\n")
    report_lines.append("6. 门诊排班信息\n")
    report_lines.append("7. 健康文章推送\n")
    report_lines.append("```\n\n")
    
    report_lines.append("#### 示例2：无预警的情况（常规结构）\n")
    report_lines.append("```\n")
    report_lines.append("1. 正向反馈与记录确认\n")
    report_lines.append("2. 血压数据评价（轻度偏高/达标）\n")
    report_lines.append("3. 生活方式建议\n")
    report_lines.append("4. 监测建议\n")
    report_lines.append("5. 门诊排班信息（可选）\n")
    report_lines.append("6. 健康文章推送\n")
    report_lines.append("```\n\n")
    
    report_lines.append("---\n\n")
    
    # 2. 需要提取的用户特征
    report_lines.append("## 2. 回复前需要提取的用户特征\n\n")
    report_lines.append("为了生成合适的回复，需要从患者的基础信息和新会话中提取以下特征：\n\n")
    
    features_required = [
        {
            "特征名称": "疾病信息",
            "来源字段": "疾病列",
            "用途": "判断疾病类型，决定预警规则和文章推送类型",
            "示例": "高血压、冠心病、高脂血症",
        },
        {
            "特征名称": "症状信息",
            "来源字段": "症状列 + 新会话",
            "用途": "判断是否需要症状预警，决定是否说明身体不适",
            "示例": "胸闷、头昏头晕、胸痛等",
        },
        {
            "特征名称": "血压数值",
            "来源字段": "新会话",
            "用途": "评价血压水平（达标/轻度偏高/中度偏高/重度偏高/低压偏低/高压偏低），判断是否需要预警",
            "提取规则": "从会话文本中提取收缩压、舒张压、脉搏值",
        },
        {
            "特征名称": "血压评价级别",
            "来源字段": "计算得出",
            "用途": "决定血压评价话术，判断是否需要预警",
            "计算规则": "根据血压数值与目标值对比，按照点评规则判断级别",
        },
        {
            "特征名称": "用药情况",
            "来源字段": "用药列 + 用药情况列",
            "用途": "判断是否需要用药相关预警（如他汀类药物副作用）",
            "示例": "苯磺酸氨氯地平片、不规律服药",
        },
        {
            "特征名称": "历史数据量",
            "来源字段": "历史会话/历史Action",
            "用途": "判断是否可以做趋势分析或对比分析",
            "注意": "本sheet页为首次发言，无历史数据",
        },
        {
            "特征名称": "生活方式",
            "来源字段": "习惯列",
            "用途": "提供个性化的生活方式建议",
            "示例": "少喝酒、心情放松、睡眠良好",
        },
    ]
    
    for feature in features_required:
        report_lines.append(f"### {feature['特征名称']}\n")
        report_lines.append(f"- **来源字段**：{feature['来源字段']}\n")
        report_lines.append(f"- **用途**：{feature['用途']}\n")
        if '提取规则' in feature:
            report_lines.append(f"- **提取规则**：{feature['提取规则']}\n")
        if '计算规则' in feature:
            report_lines.append(f"- **计算规则**：{feature['计算规则']}\n")
        if '示例' in feature:
            report_lines.append(f"- **示例**：{feature['示例']}\n")
        if '注意' in feature:
            report_lines.append(f"- **注意**：{feature['注意']}\n")
        report_lines.append("\n")
    
    report_lines.append("---\n\n")
    
    # 3. 统计分析
    report_lines.append("## 3. 统计分析\n\n")
    
    report_lines.append("### 3.1 结构出现频率统计\n\n")
    report_lines.append("| 结构元素 | 出现次数 | 出现频率 |\n")
    report_lines.append("|---------|---------|---------|\n")
    for key, count in sorted(patterns["结构出现频率"].items(), key=lambda x: x[1], reverse=True):
        percentage = round(count / len(results) * 100, 1) if results else 0
        report_lines.append(f"| {key} | {count} | {percentage}% |\n")
    report_lines.append("\n")
    
    report_lines.append("### 3.2 血压评价级别分布\n\n")
    report_lines.append("| 评价级别 | 出现次数 |\n")
    report_lines.append("|---------|---------|\n")
    for level, count in sorted(patterns["血压评价分布"].items(), key=lambda x: x[1], reverse=True):
        report_lines.append(f"| {level} | {count} |\n")
    report_lines.append("\n")
    
    report_lines.append("### 3.3 文章推送情况\n\n")
    article_stats = patterns["文章推送情况"]
    report_lines.append(f"- 有推送的记录：{article_stats['有推送']} 条\n")
    report_lines.append(f"- 无推送的记录：{article_stats['无推送']} 条\n")
    if article_stats['平均数量'] > 0:
        report_lines.append(f"- 平均推送文章数：{article_stats['平均数量']} 篇\n")
    report_lines.append("\n")
    
    # 4. 预警触发条件分析
    report_lines.append("### 3.4 预警触发条件分析\n\n")
    if patterns["预警触发条件"]:
        report_lines.append("从ext标注和实际响应中提取的预警触发条件：\n\n")
        unique_conditions = {}
        for condition in patterns["预警触发条件"]:
            key = f"{condition.get('疾病')}-{condition.get('症状')}-{condition.get('血压')}"
            if key not in unique_conditions:
                unique_conditions[key] = condition
        
        for idx, condition in enumerate(unique_conditions.values(), 1):
            report_lines.append(f"{idx}. **疾病**：{condition.get('疾病', 'N/A')}，")
            report_lines.append(f"**症状**：{condition.get('症状', 'N/A')}，")
            report_lines.append(f"**血压情况**：{condition.get('血压', 'N/A')}\n")
            if condition.get('ext标注'):
                report_lines.append(f"   - ext标注：{condition.get('ext标注')}\n")
            report_lines.append("\n")
    else:
        report_lines.append("本数据集中未发现预警触发情况。\n\n")
    
    report_lines.append("---\n\n")
    
    # 5. 与现有规则的对比
    report_lines.append("## 4. 与现有规则的对比分析\n\n")
    
    report_lines.append("### 4.1 现有规则覆盖情况\n\n")
    report_lines.append("根据对实际响应的分析，现有规则（10-blood_pressure_agent.md）基本覆盖了主要逻辑：\n\n")
    report_lines.append("✅ **已覆盖**：\n")
    report_lines.append("- 第一层预警信息判断逻辑\n")
    report_lines.append("- 单次血压数据点评规则\n")
    report_lines.append("- 症状预警规则\n")
    report_lines.append("- 正向反馈和记录确认\n")
    report_lines.append("- 就医引导和门诊排班\n")
    report_lines.append("- 健康文章推送\n\n")
    
    report_lines.append("⚠️ **需要补充或调整**：\n")
    report_lines.append("- 生活方式建议的触发条件（何时提供建议）\n")
    report_lines.append("- 监测建议的话术和触发时机\n")
    report_lines.append("- 文章推送的数量和选择逻辑（通常推送3篇）\n")
    report_lines.append("- 首次发言场景下的特殊处理（无历史数据时的引导话术）\n\n")
    
    report_lines.append("### 4.2 建议的规则调整\n\n")
    report_lines.append("1. **明确响应流程顺序**：按照上述\"响应文本的组织流程\"明确各部分的出现顺序\n")
    report_lines.append("2. **补充生活方式建议规则**：根据血压评价级别和患者习惯，提供个性化的生活方式建议\n")
    report_lines.append("3. **补充监测建议规则**：首次发言场景下，强调养成监测习惯的重要性\n")
    report_lines.append("4. **文章推送规则**：明确推送3篇相关文章，文章选择逻辑需要进一步明确\n\n")
    
    # 6. 详细案例分析（前5个示例）
    report_lines.append("---\n\n")
    report_lines.append("## 5. 详细案例分析（前5条记录）\n\n")
    
    for idx, result in enumerate(results[:5], 1):
        report_lines.append(f"### 案例 {idx}（Excel第{result['行号']}行）\n\n")
        report_lines.append(f"**患者特征**：\n")
        for key, value in result["患者特征"].items():
            report_lines.append(f"- {key}：{value}\n")
        report_lines.append("\n")
        
        if result["血压值"]:
            report_lines.append(f"**血压值**：\n")
            for key, value in result["血压值"].items():
                report_lines.append(f"- {key}：{value}\n")
            report_lines.append("\n")
        
        report_lines.append(f"**新会话**：{result['新会话']}\n\n")
        
        report_lines.append(f"**ext标注**：{result['ext标注']}\n\n")
        
        report_lines.append(f"**响应结构**：\n")
        structure = result["响应结构"]
        for key, value in structure.items():
            if isinstance(value, bool) and value:
                report_lines.append(f"- ✅ {key}\n")
            elif isinstance(value, (int, str)) and value:
                report_lines.append(f"- ✅ {key}：{value}\n")
        report_lines.append("\n")
        
        report_lines.append(f"**完整响应**（前500字符）：\n")
        report_lines.append("```\n")
        report_lines.append(result["完整响应"] + "\n")
        report_lines.append("```\n\n")
        report_lines.append("---\n\n")
    
    return "".join(report_lines)


def main():
    """主函数"""
    excel_path = project_root / "static" / "rag_source" / "uat_data" / "4.1 lsk_副本.xlsx"
    
    if not excel_path.exists():
        print(f"错误：文件不存在 {excel_path}")
        return
    
    print("正在分析Excel数据...")
    results = analyze_all_responses(excel_path)
    print(f"共分析 {len(results)} 条有效记录")
    
    print("正在聚合分析模式...")
    patterns = aggregate_patterns(results)
    
    print("正在生成分析报告...")
    report = generate_analysis_report(results, patterns, len(results))
    
    # 保存报告
    output_path = project_root / "static" / "rag_source" / "uat_data" / "01-患者首次发言的案例分析.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    
    print(f"分析完成！报告已保存至：{output_path}")


if __name__ == "__main__":
    main()
