"""
单测：_parse_json_from_output_string 对指定 JSON 字符串的解析结果。

与 backend.domain.flows.nodes.agent_creator._parse_json_from_output_string 逻辑一致，
本地复制一份避免导入链依赖（langchain 等），便于单独运行。
"""
from __future__ import annotations

import json
import unittest
from typing import Any, Dict, List, Optional


def _fix_unescaped_newlines_in_json_string(raw: str) -> str:
    """将双引号字符串值内的未转义 \\n/\\r 替换为转义形式，与 agent_creator 一致。"""
    result: List[str] = []
    in_string = False
    escape = False
    quote_char = '"'
    i = 0
    while i < len(raw):
        c = raw[i]
        if escape:
            result.append(c)
            escape = False
            i += 1
            continue
        if c == "\\" and in_string:
            result.append(c)
            escape = True
            i += 1
            continue
        if c == quote_char:
            in_string = not in_string
            result.append(c)
            i += 1
            continue
        if in_string and c == "\n":
            result.append("\\n")
            i += 1
            continue
        if in_string and c == "\r":
            result.append("\\r")
            i += 1
            continue
        result.append(c)
        i += 1
    return "".join(result)


def _parse_json_from_output_string(output: str) -> Optional[Dict[str, Any]]:
    """
    与 agent_creator._parse_json_from_output_string 实现一致（含未转义换行修复）。
    """
    if not output or not isinstance(output, str):
        return None
    s = output.strip()
    try:
        parsed = json.loads(s)
    except (json.JSONDecodeError, TypeError):
        parsed = None
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, str):
        inner = parsed.strip()
        if inner.startswith("{"):
            try:
                again = json.loads(inner)
                if isinstance(again, dict):
                    return again
            except (json.JSONDecodeError, TypeError):
                pass
            try:
                fixed_inner = _fix_unescaped_newlines_in_json_string(inner)
                again = json.loads(fixed_inner)
                if isinstance(again, dict):
                    return again
            except (json.JSONDecodeError, TypeError):
                pass
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    quote = None
    for i in range(start, len(s)):
        c = s[i]
        if escape:
            escape = False
            continue
        if c == "\\" and in_string:
            escape = True
            continue
        if not in_string:
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    substring = s[start : i + 1]
                    try:
                        return json.loads(substring)
                    except (json.JSONDecodeError, TypeError):
                        pass
                    try:
                        fixed = _fix_unescaped_newlines_in_json_string(substring)
                        return json.loads(fixed)
                    except (json.JSONDecodeError, TypeError):
                        return None
            elif c in ('"', "'"):
                in_string = True
                quote = c
        else:
            if c == quote:
                in_string = False
    return None


# 用户提供的完整输出字符串（与 agent_creator 收到的 output 一致）
# 注意：JSON 规范要求字符串值内换行为转义形式 \\n，否则整段 json.loads 会失败；本用例按合法 JSON 构造
OUTPUT_STRING = (
    '{\n  "场景描述": "患者咨询购买的不同厂家的同款药物是否可以服用，医生给出一般不建议更换厂家的回复",\n'
    '  "患者提问": "我买的药厂家不一样可以吃吗？",\n'
    '  "回复案例": "不同厂家生产的同一种药物，只要药品通用名称一致、规格相同、剂型相同，理论上主要成分和治疗作用是一致的，一般可以服用。不过由于生产工艺、辅料成分等可能存在差异，不同厂家的药物在吸收、疗效和不良反应方面可能会有细微差别。 \\n\\n'
    '服用前建议仔细核对药品的通用名称、规格、用法用量是否与医生处方一致，查看药品有效期和外观是否正常。如果是第一次更换厂家，服用期间可以多留意身体反应，观察血压控制情况以及是否有不适症状。如果对药物有任何疑问，或者服药后感觉不适，建议及时咨询医生或药师，由他们根据你的具体情况进行评估和建议。",\n'
    '  "场景": "药物相关",\n'
    '  "子场景": "能否更换厂家用药咨询",\n'
    '  "改写依据": "场景描述根据患者提问和医生回复整理；患者提问保留原意改写为清晰问句；回复案例直接使用提供内容；场景和子场景根据患者咨询的药物相关内容判定",\n'
    '  "场景置信度": 0.95,\n'
    '  "标签": {\n'
    '        "场景标签": ["药物咨询"],\n'
    '        "患者标签": [],\n'
    '        "患者发言标签": ["咨询本人用药"],\n'
    '        "回答标签": ["直接回答"],\n'
    '        "补充标签": []\n'
    "    }\n}"
)

# 线上数据：在「回复案例」值内包含真实换行（未转义），整段不是合法 JSON，需靠括号匹配 + 换行修复后解析
OUTPUT_STRING_LITERAL_NEWLINES = (
    '{\n  "场景描述": "患者咨询购买的不同厂家的同款药物是否可以服用，医生给出一般不建议更换厂家的回复",\n'
    '  "患者提问": "我买的药厂家不一样可以吃吗？",\n'
    '  "回复案例": "不同厂家生产的同一种药物，只要药品通用名称一致、规格相同、剂型相同，理论上主要成分和治疗作用是一致的，一般可以服用。不过由于生产工艺、辅料成分等可能存在差异，不同厂家的药物在吸收、疗效和不良反应方面可能会有细微差别。 '
    "\n\n"  # 真实换行，会导致整段 json.loads 失败
    '服用前建议仔细核对药品的通用名称、规格、用法用量是否与医生处方一致，查看药品有效期和外观是否正常。如果是第一次更换厂家，服用期间可以多留意身体反应，观察血压控制情况以及是否有不适症状。如果对药物有任何疑问，或者服药后感觉不适，建议及时咨询医生或药师，由他们根据你的具体情况进行评估和建议。",\n'
    '  "场景": "药物相关",\n'
    '  "子场景": "能否更换厂家用药咨询",\n'
    '  "改写依据": "场景描述根据患者提问和医生回复整理；患者提问保留原意改写为清晰问句；回复案例直接使用提供内容；场景和子场景根据患者咨询的药物相关内容判定",\n'
    '  "场景置信度": 0.95,\n'
    '  "标签": {\n'
    '        "场景标签": ["药物咨询"],\n'
    '        "患者标签": [],\n'
    '        "患者发言标签": ["咨询本人用药"],\n'
    '        "回答标签": ["直接回答"],\n'
    '        "补充标签": []\n'
    "    }\n}"
)


class TestParseJsonFromOutputStringSingle(unittest.TestCase):
    """测试 _parse_json_from_output_string 对指定字符串的解析结果。"""

    def test_parse_output_string_returns_dict(self) -> None:
        """应解析出 dict，且包含场景描述、患者提问、场景、子场景、标签等字段。"""
        result = _parse_json_from_output_string(OUTPUT_STRING)
        self.assertIsNotNone(result, "解析结果不应为 None")
        self.assertIsInstance(result, dict, "解析结果应为 dict")

        self.assertIn("场景描述", result)
        self.assertEqual(
            result["场景描述"],
            "患者咨询购买的不同厂家的同款药物是否可以服用，医生给出一般不建议更换厂家的回复",
        )
        self.assertIn("患者提问", result)
        self.assertEqual(result["患者提问"], "我买的药厂家不一样可以吃吗？")
        self.assertIn("场景", result)
        self.assertEqual(result["场景"], "药物相关")
        self.assertIn("子场景", result)
        self.assertEqual(result["子场景"], "能否更换厂家用药咨询")
        self.assertIn("改写依据", result)
        self.assertIn("场景置信度", result)
        self.assertEqual(result["场景置信度"], 0.95)
        self.assertIn("标签", result)
        self.assertIsInstance(result["标签"], dict)
        self.assertEqual(result["标签"]["场景标签"], ["药物咨询"])
        self.assertEqual(result["标签"]["患者发言标签"], ["咨询本人用药"])
        self.assertEqual(result["标签"]["回答标签"], ["直接回答"])

    def test_parse_output_string_with_literal_newlines_in_value(self) -> None:
        """「回复案例」值内含真实换行（线上数据格式）时，应通过括号匹配 + 换行修复解析出 dict。"""
        result = _parse_json_from_output_string(OUTPUT_STRING_LITERAL_NEWLINES)
        self.assertIsNotNone(result, "线上格式（值内真实换行）应解析出 dict，不应返回 None")
        self.assertIsInstance(result, dict)
        self.assertEqual(
            result["场景描述"],
            "患者咨询购买的不同厂家的同款药物是否可以服用，医生给出一般不建议更换厂家的回复",
        )
        self.assertEqual(result["患者提问"], "我买的药厂家不一样可以吃吗？")
        self.assertEqual(result["场景"], "药物相关")
        self.assertEqual(result["子场景"], "能否更换厂家用药咨询")
        self.assertIn("回复案例", result)
        self.assertIn("服用前建议仔细核对", result["回复案例"])


if __name__ == "__main__":
    unittest.main()
