#!/usr/bin/env python
"""
血压会话响应模式分析 V2

从头重新分析Excel中两个sheet页的"新会话响应"列的回答套路
分析sheet页：
1. "患者有数据（无历史会话，无历史action）"
2. "1218患者有数据（无历史会话，无历史action）"
"""
import sys
import os
from pathlib import Path
import pandas as pd
import re
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict, Counter

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class ResponseAnalyzer:
    """响应分析器"""
    
    def __init__(self):
        self.patterns = {
            "正向反馈": [
                r"习惯非常棒", r"习惯非常好", r"主动监测", r"帮你记录", 
                r"记录了这次", r"记录了今天", r"记录下今天", r"保存了今天"
            ],
            "记录确认": [
                r"已经帮你记录", r"已经记录", r"帮你保存", r"记录下", 
                r"记录了", r"保存了"
            ],
            "血压评价": {
                "达标": [
                    r"正常范围", r"在目标范围内", r"正常高值范围", 
                    r"整体情况良好", r"达标", r"正常区间"
                ],
                "轻度偏高": [
                    r"轻度偏高", r"略高", r"稍微偏高", r"稍微升高"
                ],
                "中度偏高": [
                    r"中度偏高", r"明显高于正常范围", r"需要关注", 
                    r"高于正常范围"
                ],
                "重度偏高": [
                    r"重度偏高", r"比较严重", r"需要紧急", r"尽快就医",
                    r">=180", r">=110", r"明显的健康风险"
                ],
                "低压偏低": [
                    r"低压偏低", r"舒张压.*偏低"
                ],
                "高压偏低": [
                    r"高压偏低", r"收缩压.*偏低"
                ]
            },
            "症状说明": [
                r"身体不适", r"不舒服", r"身体反应", r"需要特别留意",
                r"可能会出现"
            ],
            "预警信息": [
                r"需要重视", r"引起重视", r"尽快就医", r"尽快回院",
                r"需要关注", r"需预警", r"高度重视", r"需要引起"
            ],
            "就医引导": [
                r"建议你尽快", r"尽快前往医院", r"让医生评估", 
                r"医生.*专业建议", r"建议.*就医"
            ],
            "门诊排班": [
                r"门诊排班", r"出诊时间", r"scheduleStartDay", 
                r"查看医生", r"就诊时间"
            ],
            "生活方式建议": [
                r"注意休息", r"低盐饮食", r"适度运动", r"轻度运动",
                r"保持.*饮食", r"避免.*劳累", r"生活习惯", r"生活方式的调整",
                r"情绪波动", r"散步"
            ],
            "监测建议": [
                r"继续监测", r"规律监测", r"坚持监测", r"继续坚持",
                r"记录更多数据", r"持续监测", r"定期监测", 
                r"每天固定时间", r"早晚各测量", r"养成.*习惯"
            ],
            "趋势分析": [
                r"血压趋势图", r"趋势图", r"变化趋势", r"趋势分析",
                r"血压变化趋势", r"查看血压趋势"
            ],
            "对比分析": [
                r"相比", r"上次", r"之前", r"对比", r"与.*相比"
            ],
            "文章推送": [
                r"articleId=", r"健康科普文章", r"科普文章", r"相关文章"
            ]
        }
    
    def extract_patient_info(self, row: pd.Series) -> Dict[str, Any]:
        """提取患者基础信息（从疾病列到习惯列）"""
        info = {}
        fields = ["疾病", "血压", "症状", "用药", "用药情况", "习惯"]
        
        for field in fields:
            value = row.get(field)
            if pd.notna(value):
                value_str = str(value).strip()
                if value_str and value_str != "无" and value_str.lower() != "nan":
                    info[field] = value_str
        
        # 添加年龄
        age = row.get("年龄")
        if pd.notna(age):
            try:
                info["年龄"] = int(age)
            except:
                info["年龄"] = str(age).strip()
        
        return info
    
    def extract_bp_from_session(self, session_text: str) -> Optional[Dict[str, int]]:
        """从新会话文本中提取血压和脉搏值"""
        if not session_text or pd.isna(session_text):
            return None
        
        text = str(session_text)
        result = {}
        
        # 提取收缩压（高压）
        sbp_patterns = [
            r"高压[：:]?\s*(\d+)",
            r"收缩压[：:]?\s*(\d+)",
            r"高[：:]?\s*(\d+)",
        ]
        for pattern in sbp_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["收缩压"] = int(match.group(1))
                break
        
        # 提取舒张压（低压）
        dbp_patterns = [
            r"低压[：:]?\s*(\d+)",
            r"舒张压[：:]?\s*(\d+)",
            r"低[：:]?\s*(\d+)",
        ]
        for pattern in dbp_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["舒张压"] = int(match.group(1))
                break
        
        # 提取脉搏
        pulse_patterns = [
            r"脉搏[：:]?\s*(\d+)",
            r"心率[：:]?\s*(\d+)",
            r"BPM[：:]?\s*(\d+)",
        ]
        for pattern in pulse_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["脉搏"] = int(match.group(1))
                break
        
        return result if result else None
    
    def analyze_response_structure(self, response_text: str, bp_status: str = None) -> Dict[str, Any]:
        """分析响应文本的结构"""
        if not response_text or pd.isna(response_text):
            return {}
        
        text = str(response_text)
        structure = {
            "正向反馈": False,
            "记录确认": False,
            "血压评价": False,
            "血压评价级别": None,
            "症状说明": False,
            "预警信息": False,
            "预警类型": None,
            "就医引导": False,
            "门诊排班": False,
            "生活方式建议": False,
            "监测建议": False,
            "趋势分析": False,
            "对比分析": False,
            "文章推送": False,
            "文章数量": 0,
            "响应片段": []  # 用于记录响应文本的关键片段
        }
        
        # 1. 正向反馈和记录确认
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in self.patterns["正向反馈"]):
            structure["正向反馈"] = True
            structure["记录确认"] = True
        
        # 检查记录确认的其他模式
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in self.patterns["记录确认"]):
            structure["记录确认"] = True
        
        # 2. 血压评价（优先从bp_status提取）
        bp_level = None
        if bp_status and pd.notna(bp_status):
            bp_status_str = str(bp_status)
            for level in ["重度偏高", "中度偏高", "轻度偏高", "高压偏低", "低压偏低", "达标"]:
                if level in bp_status_str:
                    bp_level = level
                    break
        
        # 如果从bp_status没找到，从文本中提取
        if not bp_level:
            for level, patterns in self.patterns["血压评价"].items():
                for pattern in patterns:
                    if re.search(pattern, text, re.IGNORECASE):
                        bp_level = level
                        break
                if bp_level:
                    break
        
        if bp_level:
            structure["血压评价"] = True
            structure["血压评价级别"] = bp_level
        
        # 3. 症状说明
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in self.patterns["症状说明"]):
            structure["症状说明"] = True
        
        # 4. 预警信息
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in self.patterns["预警信息"]):
            structure["预警信息"] = True
            # 判断预警类型
            if any(keyword in text for keyword in ["血压", "偏高", "偏低"]):
                structure["预警类型"] = "血压预警"
            elif any(keyword in text for keyword in ["症状", "不适", "胸闷", "头晕", "胸痛"]):
                structure["预警类型"] = "症状预警"
            elif any(keyword in text for keyword in ["脉搏", "心率", "BPM"]):
                structure["预警类型"] = "脉搏预警"
            else:
                structure["预警类型"] = "其他预警"
        
        # 5. 就医引导
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in self.patterns["就医引导"]):
            structure["就医引导"] = True
        
        # 6. 门诊排班
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in self.patterns["门诊排班"]):
            structure["门诊排班"] = True
        
        # 7. 生活方式建议
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in self.patterns["生活方式建议"]):
            structure["生活方式建议"] = True
        
        # 8. 监测建议
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in self.patterns["监测建议"]):
            structure["监测建议"] = True
        
        # 9. 趋势分析
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in self.patterns["趋势分析"]):
            structure["趋势分析"] = True
        
        # 10. 对比分析
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in self.patterns["对比分析"]):
            structure["对比分析"] = True
        
        # 11. 文章推送
        article_matches = re.findall(r"articleId=(\d+)", text)
        if article_matches or any(re.search(pattern, text, re.IGNORECASE) for pattern in self.patterns["文章推送"]):
            structure["文章推送"] = True
            structure["文章数量"] = len(article_matches) if article_matches else 0
        
        # 提取关键响应片段（用于分析话术模式）
        self._extract_response_snippets(text, structure)
        
        return structure
    
    def _extract_response_snippets(self, text: str, structure: Dict[str, Any]):
        """提取响应文本的关键片段"""
        snippets = []
        
        # 提取正向反馈片段
        if structure["正向反馈"]:
            match = re.search(r"(.{0,50}(?:习惯|监测|记录).{0,50})", text, re.IGNORECASE)
            if match:
                snippets.append(("正向反馈", match.group(1).strip()))
        
        # 提取血压评价片段
        if structure["血压评价"]:
            match = re.search(r"(.{0,80}(?:血压|高压|低压).{0,80})", text, re.IGNORECASE)
            if match:
                snippets.append(("血压评价", match.group(1).strip()[:150]))
        
        # 提取预警片段
        if structure["预警信息"]:
            match = re.search(r"(.{0,80}(?:重视|关注|就医|回院).{0,80})", text, re.IGNORECASE)
            if match:
                snippets.append(("预警", match.group(1).strip()[:150]))
        
        structure["响应片段"] = snippets


def analyze_sheet(excel_path: Path, sheet_name: str) -> List[Dict[str, Any]]:
    """分析单个sheet页"""
    analyzer = ResponseAnalyzer()
    df = pd.read_excel(excel_path, sheet_name=sheet_name)
    
    results = []
    
    for idx, row in df.iterrows():
        # 跳过空行
        new_session = row.get("新会话")
        new_session_response = row.get("新会话响应")
        if pd.isna(new_session) or pd.isna(new_session_response):
            continue
        
        # 提取患者信息
        patient_info = analyzer.extract_patient_info(row)
        
        # 提取血压值
        bp_values = analyzer.extract_bp_from_session(str(new_session))
        
        # 获取血压状态
        bp_status = str(row.get("血压", "")).strip() if pd.notna(row.get("血压")) else None
        
        # 分析响应结构
        response_structure = analyzer.analyze_response_structure(
            str(new_session_response), 
            bp_status
        )
        
        # 获取ext标注
        ext_note = str(row.get("ext", "")).strip() if pd.notna(row.get("ext")) else ""
        
        results.append({
            "sheet_name": sheet_name,
            "row_num": idx + 2,
            "patient_info": patient_info,
            "bp_values": bp_values,
            "bp_status": bp_status,
            "new_session": str(new_session)[:150] + "..." if len(str(new_session)) > 150 else str(new_session),
            "response_structure": response_structure,
            "ext_note": ext_note,
            "full_response": str(new_session_response)[:600] + "..." if len(str(new_session_response)) > 600 else str(new_session_response),
        })
    
    return results


def aggregate_statistics(all_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """聚合统计信息"""
    stats = {
        "total_count": len(all_results),
        "structure_frequency": defaultdict(int),
        "bp_level_distribution": defaultdict(int),
        "warning_conditions": [],
        "article_stats": {"有推送": 0, "无推送": 0, "平均数量": 0, "数量分布": defaultdict(int)},
        "response_flow_patterns": [],
    }
    
    total_articles = 0
    articles_count = 0
    
    for result in all_results:
        structure = result["response_structure"]
        patient_info = result["patient_info"]
        
        # 统计结构出现频率
        for key, value in structure.items():
            if key in ["响应片段"]:
                continue
            if isinstance(value, bool) and value:
                stats["structure_frequency"][key] += 1
            elif isinstance(value, (int, str)) and value:
                if key == "血压评价级别":
                    stats["bp_level_distribution"][value] += 1
                stats["structure_frequency"][f"{key}:{value}"] += 1
        
        # 收集预警条件
        if structure.get("预警信息"):
            warning_condition = {
                "疾病": patient_info.get("疾病"),
                "症状": patient_info.get("症状"),
                "血压状态": result.get("bp_status"),
                "ext标注": result.get("ext_note"),
            }
            stats["warning_conditions"].append(warning_condition)
        
        # 统计文章推送
        if structure.get("文章推送"):
            stats["article_stats"]["有推送"] += 1
            article_count = structure.get("文章数量", 0)
            if article_count > 0:
                total_articles += article_count
                articles_count += 1
                stats["article_stats"]["数量分布"][article_count] += 1
        else:
            stats["article_stats"]["无推送"] += 1
        
        # 记录响应流程模式
        flow_elements = []
        if structure.get("正向反馈"):
            flow_elements.append("正向反馈")
        if structure.get("记录确认"):
            flow_elements.append("记录确认")
        if structure.get("血压评价"):
            flow_elements.append(f"血压评价({structure.get('血压评价级别', 'N/A')})")
        if structure.get("症状说明"):
            flow_elements.append("症状说明")
        if structure.get("预警信息"):
            flow_elements.append("预警信息")
        if structure.get("就医引导"):
            flow_elements.append("就医引导")
        if structure.get("门诊排班"):
            flow_elements.append("门诊排班")
        if structure.get("生活方式建议"):
            flow_elements.append("生活方式建议")
        if structure.get("监测建议"):
            flow_elements.append("监测建议")
        if structure.get("趋势分析"):
            flow_elements.append("趋势分析")
        if structure.get("文章推送"):
            flow_elements.append("文章推送")
        
        stats["response_flow_patterns"].append(" → ".join(flow_elements))
    
    # 计算平均文章数量
    if articles_count > 0:
        stats["article_stats"]["平均数量"] = round(total_articles / articles_count, 2)
    
    return stats


def generate_report(sheet_results: Dict[str, List[Dict[str, Any]]], 
                   all_stats: Dict[str, Any]) -> str:
    """生成分析报告"""
    lines = []
    
    lines.append("# 患者首次发言的案例分析（Sheet 2 & 3）\n\n")
    lines.append("## 数据概览\n\n")
    
    for sheet_name, results in sheet_results.items():
        lines.append(f"- **{sheet_name}**：{len(results)} 条有效记录\n")
    
    lines.append(f"- **总计**：{all_stats['total_count']} 条有效记录\n\n")
    lines.append("---\n\n")
    
    # 1. 响应文本组织流程
    lines.append("## 1. 响应文本的组织流程（全量结构）\n\n")
    lines.append("基于对所有响应文本的深入分析，响应文本的组织流程如下：\n\n")
    
    # 分析流程步骤
    flow_steps = [
        {
            "name": "正向反馈",
            "key": "正向反馈",
            "necessity": "必需",
            "description": "对患者主动监测行为的肯定和表扬",
            "frequency": all_stats["structure_frequency"].get("正向反馈", 0)
        },
        {
            "name": "记录确认",
            "key": "记录确认",
            "necessity": "必需",
            "description": "确认已记录患者的血压数据",
            "frequency": all_stats["structure_frequency"].get("记录确认", 0)
        },
        {
            "name": "血压数据评价",
            "key": "血压评价",
            "necessity": "必需",
            "description": "对本次血压值进行评价，包括达标/轻度偏高/中度偏高/重度偏高/低压偏低/高压偏低",
            "frequency": sum(1 for k in all_stats["structure_frequency"].keys() if k.startswith("血压评价"))
        },
        {
            "name": "症状说明",
            "key": "症状说明",
            "necessity": "条件必需",
            "description": "当患者有症状时，说明血压异常可能引起的身体不适反应",
            "frequency": all_stats["structure_frequency"].get("症状说明", 0)
        },
        {
            "name": "预警信息提示",
            "key": "预警信息",
            "necessity": "条件必需",
            "description": "当触发预警条件时（血压异常/症状/脉搏异常），提示患者需要重视",
            "frequency": all_stats["structure_frequency"].get("预警信息", 0)
        },
        {
            "name": "就医引导",
            "key": "就医引导",
            "necessity": "条件必需",
            "description": "当需要就医时，引导患者尽快前往医院就诊，寻求专业医疗建议",
            "frequency": all_stats["structure_frequency"].get("就医引导", 0)
        },
        {
            "name": "门诊排班信息",
            "key": "门诊排班",
            "necessity": "常见",
            "description": "提供医生门诊排班查询功能，方便患者安排就诊时间",
            "frequency": all_stats["structure_frequency"].get("门诊排班", 0)
        },
        {
            "name": "生活方式建议",
            "key": "生活方式建议",
            "necessity": "条件必需",
            "description": "根据患者血压情况和习惯，提供个性化的生活方式调整建议（饮食、运动、作息等）",
            "frequency": all_stats["structure_frequency"].get("生活方式建议", 0)
        },
        {
            "name": "监测建议",
            "key": "监测建议",
            "necessity": "条件必需",
            "description": "建议患者继续规律监测血压，养成持续监测的习惯",
            "frequency": all_stats["structure_frequency"].get("监测建议", 0)
        },
        {
            "name": "趋势分析",
            "key": "趋势分析",
            "necessity": "条件必需",
            "description": "当有足够历史数据时，进行血压趋势分析（本场景为首次发言，无此情况）",
            "frequency": all_stats["structure_frequency"].get("趋势分析", 0)
        },
        {
            "name": "对比分析",
            "key": "对比分析",
            "necessity": "条件必需",
            "description": "当有上次记录时，进行对比分析（本场景为首次发言，无此情况）",
            "frequency": all_stats["structure_frequency"].get("对比分析", 0)
        },
        {
            "name": "健康文章推送",
            "key": "文章推送",
            "necessity": "常见",
            "description": "推送相关的健康科普文章，帮助患者了解更多知识",
            "frequency": all_stats["structure_frequency"].get("文章推送", 0)
        },
    ]
    
    total = all_stats["total_count"]
    for step in flow_steps:
        lines.append(f"### {step['name']}\n\n")
        lines.append(f"- **必要性**：{step['necessity']}\n")
        freq = step['frequency']
        pct = round(freq / total * 100, 1) if total > 0 else 0
        lines.append(f"- **出现频率**：{freq} 次 ({pct}%)\n")
        lines.append(f"- **说明**：{step['description']}\n\n")
    
    # 典型流程示例
    lines.append("### 典型响应流程示例\n\n")
    
    # 统计最常见的流程模式
    flow_counter = Counter(all_stats["response_flow_patterns"])
    most_common_flows = flow_counter.most_common(3)
    
    for i, (flow, count) in enumerate(most_common_flows, 1):
        pct = round(count / total * 100, 1) if total > 0 else 0
        lines.append(f"#### 示例{i}：{count}次 ({pct}%)\n")
        lines.append("```\n")
        steps = flow.split(" → ")
        for j, step in enumerate(steps, 1):
            lines.append(f"{j}. {step}\n")
        lines.append("```\n\n")
    
    lines.append("---\n\n")
    
    # 2. 需要提取的用户特征
    lines.append("## 2. 回复前需要提取的用户特征\n\n")
    lines.append("为了生成合适的回复，需要从患者的基础信息和新会话中提取以下特征：\n\n")
    
    features = [
        {
            "name": "疾病信息",
            "source": "疾病列",
            "usage": "判断疾病类型（高血压/冠心病/高脂血症等），决定预警规则和文章推送类型",
            "example": "高血压、冠心病、高脂血症、糖尿病等"
        },
        {
            "name": "症状信息",
            "source": "症状列 + 新会话文本",
            "usage": "判断是否需要症状预警，决定是否说明身体不适反应",
            "example": "胸闷、头昏头晕、胸痛、恶心腹胀、乏力等"
        },
        {
            "name": "血压数值",
            "source": "新会话文本",
            "usage": "核心数据，用于评价血压水平、判断预警级别",
            "extraction": "从会话文本中提取收缩压、舒张压、脉搏值（使用正则表达式匹配）"
        },
        {
            "name": "血压评价级别",
            "source": "计算得出",
            "usage": "决定血压评价话术、判断是否需要预警",
            "calculation": "根据血压数值与目标值对比，按照点评规则判断：达标/轻度偏高/中度偏高/重度偏高/低压偏低/高压偏低"
        },
        {
            "name": "用药情况",
            "source": "用药列 + 用药情况列",
            "usage": "判断是否需要用药相关预警（如他汀类药物副作用导致肌肉症状）",
            "example": "苯磺酸氨氯地平片、不规律服药、规律服药"
        },
        {
            "name": "生活方式习惯",
            "source": "习惯列",
            "usage": "提供个性化的生活方式建议，参考患者现有习惯进行调整",
            "example": "少喝酒、心情放松、睡眠良好、运动、少吃盐、不抽烟"
        },
        {
            "name": "历史数据量",
            "source": "历史会话/历史Action",
            "usage": "判断是否可以做趋势分析或对比分析",
            "note": "本场景为首次发言，无历史数据"
        },
    ]
    
    for feature in features:
        lines.append(f"### {feature['name']}\n\n")
        lines.append(f"- **来源字段**：{feature['source']}\n")
        lines.append(f"- **用途**：{feature['usage']}\n")
        if 'extraction' in feature:
            lines.append(f"- **提取规则**：{feature['extraction']}\n")
        if 'calculation' in feature:
            lines.append(f"- **计算规则**：{feature['calculation']}\n")
        if 'example' in feature:
            lines.append(f"- **示例**：{feature['example']}\n")
        if 'note' in feature:
            lines.append(f"- **注意**：{feature['note']}\n")
        lines.append("\n")
    
    lines.append("---\n\n")
    
    # 3. 统计分析
    lines.append("## 3. 统计分析\n\n")
    
    lines.append("### 3.1 结构元素出现频率统计\n\n")
    lines.append("| 结构元素 | 出现次数 | 出现频率 |\n")
    lines.append("|---------|---------|---------|\n")
    
    # 排序并输出
    sorted_freq = sorted(all_stats["structure_frequency"].items(), 
                        key=lambda x: x[1], reverse=True)
    for key, count in sorted_freq[:20]:  # 显示前20个
        pct = round(count / total * 100, 1) if total > 0 else 0
        lines.append(f"| {key} | {count} | {pct}% |\n")
    lines.append("\n")
    
    lines.append("### 3.2 血压评价级别分布\n\n")
    lines.append("| 评价级别 | 出现次数 | 占比 |\n")
    lines.append("|---------|---------|------|\n")
    for level, count in sorted(all_stats["bp_level_distribution"].items(), 
                               key=lambda x: x[1], reverse=True):
        pct = round(count / total * 100, 1) if total > 0 else 0
        lines.append(f"| {level} | {count} | {pct}% |\n")
    lines.append("\n")
    
    lines.append("### 3.3 文章推送情况\n\n")
    article_stats = all_stats["article_stats"]
    lines.append(f"- **有推送的记录**：{article_stats['有推送']} 条\n")
    lines.append(f"- **无推送的记录**：{article_stats['无推送']} 条\n")
    if article_stats['平均数量'] > 0:
        lines.append(f"- **平均推送文章数**：{article_stats['平均数量']} 篇\n")
        lines.append(f"- **文章数量分布**：\n")
        for count, freq in sorted(article_stats['数量分布'].items()):
            lines.append(f"  - {count}篇：{freq} 次\n")
    lines.append("\n")
    
    lines.append("### 3.4 预警触发条件分析\n\n")
    if all_stats["warning_conditions"]:
        lines.append("从ext标注和实际响应中提取的预警触发条件（去重后）：\n\n")
        
        # 去重
        unique_conditions = {}
        for condition in all_stats["warning_conditions"]:
            key = f"{condition.get('疾病')}-{condition.get('症状')}-{condition.get('血压状态')}"
            if key not in unique_conditions:
                unique_conditions[key] = condition
        
        for idx, condition in enumerate(list(unique_conditions.values())[:30], 1):
            lines.append(f"{idx}. **疾病**：{condition.get('疾病', 'N/A')}，")
            lines.append(f"**症状**：{condition.get('症状', 'N/A')}，")
            lines.append(f"**血压状态**：{condition.get('血压状态', 'N/A')}\n")
            if condition.get('ext标注'):
                lines.append(f"   - ext标注：{condition.get('ext标注')[:100]}\n")
            lines.append("\n")
        
        if len(unique_conditions) > 30:
            lines.append(f"\n（共{len(unique_conditions)}种不同的预警触发条件组合）\n\n")
    else:
        lines.append("本数据集中未发现预警触发情况。\n\n")
    
    lines.append("---\n\n")
    
    # 4. 与现有规则的对比
    lines.append("## 4. 与现有规则的对比分析\n\n")
    
    lines.append("### 4.1 现有规则覆盖情况\n\n")
    lines.append("根据对实际响应的分析，现有规则（10-blood_pressure_agent.md）的覆盖情况：\n\n")
    lines.append("✅ **已覆盖**：\n")
    lines.append("- 第一层预警信息判断逻辑\n")
    lines.append("- 单次血压数据点评规则\n")
    lines.append("- 症状预警规则\n")
    lines.append("- 正向反馈和记录确认\n")
    lines.append("- 就医引导和门诊排班\n")
    lines.append("- 健康文章推送\n\n")
    
    lines.append("⚠️ **需要补充或调整**：\n")
    lines.append("- 响应流程的明确顺序（各部分的出现顺序和组合规则）\n")
    lines.append("- 生活方式建议的触发条件和个性化规则\n")
    lines.append("- 监测建议的话术和触发时机（首次发言场景）\n")
    lines.append("- 文章推送的数量选择逻辑（通常推送3篇）\n")
    lines.append("- 不同血压评价级别对应的不同响应结构\n\n")
    
    lines.append("### 4.2 建议的规则调整\n\n")
    lines.append("1. **明确响应流程顺序**：按照上述\"响应文本的组织流程\"明确各部分的出现顺序和组合规则\n")
    lines.append("2. **补充生活方式建议规则**：根据血压评价级别和患者现有习惯，提供个性化的生活方式建议\n")
    lines.append("3. **补充监测建议规则**：首次发言场景下，强调养成持续监测习惯的重要性，明确监测频率建议\n")
    lines.append("4. **文章推送规则细化**：明确推送3篇相关文章，并说明文章选择逻辑（根据疾病类型选择）\n")
    lines.append("5. **区分不同场景的响应结构**：根据是否有预警、血压评价级别等因素，区分不同的响应结构模板\n\n")
    
    lines.append("---\n\n")
    
    # 5. 两个sheet页的对比分析
    if len(sheet_results) > 1:
        lines.append("## 5. 两个Sheet页的数据对比\n\n")
        for sheet_name, results in sheet_results.items():
            lines.append(f"### {sheet_name}\n\n")
            lines.append(f"- 记录数：{len(results)} 条\n")
            
            # 统计该sheet的结构频率
            sheet_freq = defaultdict(int)
            sheet_bp_level = defaultdict(int)
            for result in results:
                structure = result["response_structure"]
                for key, value in structure.items():
                    if isinstance(value, bool) and value:
                        sheet_freq[key] += 1
                    elif key == "血压评价级别" and value:
                        sheet_bp_level[value] += 1
            
            lines.append(f"- **结构频率**（前10项）：\n")
            for key, count in sorted(sheet_freq.items(), key=lambda x: x[1], reverse=True)[:10]:
                pct = round(count / len(results) * 100, 1) if results else 0
                lines.append(f"  - {key}：{count}次 ({pct}%)\n")
            
            lines.append(f"- **血压评价级别分布**：\n")
            for level, count in sorted(sheet_bp_level.items(), key=lambda x: x[1], reverse=True):
                pct = round(count / len(results) * 100, 1) if results else 0
                lines.append(f"  - {level}：{count}次 ({pct}%)\n")
            lines.append("\n")
    
    lines.append("---\n\n")
    
    # 6. 详细案例分析
    lines.append("## 6. 详细案例分析（每个Sheet页前3条记录）\n\n")
    
    for sheet_name, results in sheet_results.items():
        lines.append(f"### {sheet_name}\n\n")
        
        for idx, result in enumerate(results[:3], 1):
            lines.append(f"#### 案例 {idx}（Excel第{result['row_num']}行）\n\n")
            
            lines.append("**患者特征**：\n")
            for key, value in result["patient_info"].items():
                lines.append(f"- {key}：{value}\n")
            lines.append("\n")
            
            if result["bp_values"]:
                lines.append("**血压值**：\n")
                for key, value in result["bp_values"].items():
                    lines.append(f"- {key}：{value}\n")
                lines.append("\n")
            
            if result.get("bp_status"):
                lines.append(f"**血压状态**：{result['bp_status']}\n\n")
            
            lines.append(f"**新会话**：{result['new_session']}\n\n")
            
            if result["ext_note"]:
                lines.append(f"**ext标注**：{result['ext_note'][:200]}\n\n")
            
            lines.append("**响应结构**：\n")
            structure = result["response_structure"]
            for key, value in structure.items():
                if key in ["响应片段"]:
                    continue
                if isinstance(value, bool) and value:
                    lines.append(f"- ✅ {key}\n")
                elif isinstance(value, (int, str)) and value:
                    lines.append(f"- ✅ {key}：{value}\n")
            lines.append("\n")
            
            if structure.get("响应片段"):
                lines.append("**关键响应片段**：\n")
                for snippet_type, snippet_text in structure["响应片段"]:
                    lines.append(f"- **{snippet_type}**：{snippet_text}\n")
                lines.append("\n")
            
            lines.append("**完整响应**（前600字符）：\n")
            lines.append("```\n")
            lines.append(result["full_response"] + "\n")
            lines.append("```\n\n")
            lines.append("---\n\n")
    
    return "".join(lines)


def main():
    """主函数"""
    excel_path = project_root / "static" / "rag_source" / "uat_data" / "4.1 lsk_副本.xlsx"
    
    if not excel_path.exists():
        print(f"错误：文件不存在 {excel_path}")
        return
    
    # 要分析的sheet页
    sheet_names = [
        "患者有数据（无历史会话，无历史action）",
        "1218患者有数据（无历史会话，无历史action）"
    ]
    
    print("开始分析Excel数据...")
    sheet_results = {}
    all_results = []
    
    for sheet_name in sheet_names:
        print(f"  正在分析：{sheet_name}...")
        results = analyze_sheet(excel_path, sheet_name)
        sheet_results[sheet_name] = results
        all_results.extend(results)
        print(f"    完成：{len(results)} 条记录")
    
    print(f"\n共分析 {len(all_results)} 条有效记录")
    
    print("正在聚合统计信息...")
    all_stats = aggregate_statistics(all_results)
    
    print("正在生成分析报告...")
    report = generate_report(sheet_results, all_stats)
    
    # 保存报告
    output_path = project_root / "static" / "rag_source" / "uat_data" / "02-患者首次发言的案例分析.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    
    print(f"分析完成！报告已保存至：{output_path}")


if __name__ == "__main__":
    main()
