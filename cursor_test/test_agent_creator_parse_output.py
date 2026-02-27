"""
单元测试：agent_creator 输出解析逻辑（192-193 行等价逻辑）。

验证三种 LLM 返回格式均能正确解析为 dict 并得到 edges_var 所需字段：
- Untitled-1 / Untitled-2：content 为字符串（可能一层或两层 JSON 编码）；
- Untitled-3：content 已为 dict。
"""
from __future__ import annotations

import json
import unittest
from typing import Any, Dict, Optional


# ---------- 正确的解析逻辑（应在 agent_creator 中与 192-193 等价） ----------


def parse_content_to_output_data(content: Any) -> Optional[Dict[str, Any]]:
    """
    将 LLM 返回的 content 统一解析为业务 dict（用于写入 edges_var）。

    支持：
    1. content 已是 dict → 直接返回；
    2. content 为 str 且一次 json.loads 得到 dict → 返回；
    3. content 为 str 且一次 json.loads 得到 str（双层编码）→ 再解析一次返回 dict；
    4. content 为 str 但整段解析失败 → 从第一个 '{' 起括号匹配截取后解析。
    """
    if content is None:
        return None
    if isinstance(content, dict):
        return content

    if not isinstance(content, str) or not content.strip():
        return None

    s = content.strip()

    # 1）整段解析
    try:
        parsed = json.loads(s)
    except (json.JSONDecodeError, TypeError):
        parsed = None

    if isinstance(parsed, dict):
        return parsed
    # 2）一次解析得到的是字符串（双层编码）：再解析一次
    if isinstance(parsed, str):
        inner = parsed.strip()
        if inner.startswith("{"):
            try:
                again = json.loads(inner)
                if isinstance(again, dict):
                    return again
            except (json.JSONDecodeError, TypeError):
                pass

    # 3）括号匹配截取根对象
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
                    try:
                        return json.loads(s[start : i + 1])
                    except (json.JSONDecodeError, TypeError):
                        return None
            elif c in ('"', "'"):
                in_string = True
                quote = c
        else:
            if c == quote:
                in_string = False
    return None


def content_to_edges_var_ready(content: Any) -> Optional[Dict[str, Any]]:
    """
    与 agent_creator 192-193 行等价：从 content 得到可用于 _apply_output_data_to_edges_var 的 dict。
    返回 dict 则视为「逻辑计算成功」。
    """
    parsed = parse_content_to_output_data(content)
    if isinstance(parsed, dict):
        return parsed
    return None


# ---------- 测试数据（与 Untitled-1 / Untitled-2 / Untitled-3 同结构） ----------


# Untitled-1：content 为字符串，一层 JSON（整段即对象）
PAYLOAD_UNTITLED_1 = {
    "role": "assistant",
    "content": (
        "{\n  \"场景描述\": \"患者咨询购买到的不同厂家的同一种药物是否可以服用，医生给出一般不建议更换厂家的初步回复\",\n"
        "  \"患者提问\": \"我买的药厂家不一样可以吃吗？\",\n"
        "  \"回复案例\": \"不同厂家生产的同一种药物，只要药品通用名称一致、规格相同、剂型相同，理论上主要成分和治疗作用是一致的，一般可以服用。\",\n"
        "  \"场景\": \"药物相关\",\n"
        "  \"子场景\": \"药物替换咨询\",\n"
        "  \"改写依据\": \"场景描述结合患者提问和医生初步回复整理\",\n"
        "  \"场景置信度\": 0.95,\n"
        "  \"标签\": {\n"
        "        \"场景标签\": [\"药物替换咨询\"],\n"
        "        \"患者标签\": [],\n"
        "        \"患者发言标签\": [\"咨询本人\", \"疑问语气\"],\n"
        "        \"回答标签\": [\"直接回答\"],\n"
        "        \"补充标签\": []\n"
        "    }\n}"
    ),
    "additional_kwargs": {"refusal": None},
}

# Untitled-2：content 为字符串，一层 JSON（长文本，含 } 等字符）
PAYLOAD_UNTITLED_2 = {
    "role": "assistant",
    "content": (
        "{\n  \"场景描述\": \"68岁的高血压、糖尿病、高脂血症患者，存在不规律服药情况，今日自测血压高压167mmHg、低压89mmHg，属于中度偏高，脉搏72次/分，为正常范围，患者还存在夜尿增多的症状。\",\n"
        "  \"患者提问\": \"我今天自测高压167mmHg，低压89mmHg，脉搏72次/分，请帮忙记录并给出相关建议\",\n"
        "  \"回复案例\": \"你能主动监测并告诉我血压情况，这个习惯非常棒！已经帮你记录了今天的血压数据。\\n你今天测量的血压值为167/89mmHg。\\n考虑尽快到[医院]就诊。\\nscheduleStartDay=[日期], scheduleEndDay=[日期]\\ncontent=\\n\",\n"
        "  \"场景\": \"记录血压\",\n"
        "  \"子场景\": \"血压记录与异常反馈\",\n"
        "  \"改写依据\": \"场景描述结合患者年龄、基础疾病、用药情况、症状及本次自测的血压脉搏数据\",\n"
        "  \"场景置信度\": 0.95,\n"
        "  \"标签\": {\n"
        "        \"场景标签\": [\"血压记录\", \"血压异常\"],\n"
        "        \"患者标签\": [\"68岁\", \"高血压\", \"糖尿病\", \"高脂血症\"],\n"
        "        \"患者发言标签\": [\"陈述自测数据\", \"咨询本人情况\"],\n"
        "        \"回答标签\": [\"专业指导\", \"有推荐文章\", \"引导就诊\"],\n"
        "        \"补充标签\": []\n"
        "    }\n}"
    ),
    "additional_kwargs": {"refusal": None},
}

# Untitled-3：content 已为 dict
PAYLOAD_UNTITLED_3 = {
    "role": "assistant",
    "content": {
        "场景描述": "患者向医护人员数字分身咨询[医院]五楼住院处张斌助理的联系电话",
        "患者提问": "请问[医院]五楼住院处张斌助理的联系电话是多少？",
        "回复案例": "作为医生的数字分身，当前可以为你提供高血压慢病健康管理及科学指导，你咨询的此类问题暂无法回复，建议你通过医院的官方渠道直接咨询。",
        "场景": "院内资源/政策咨询",
        "子场景": "咨询工作人员联系电话",
        "改写依据": "场景描述、患者提问对敏感信息进行脱敏",
        "场景置信度": 1,
        "标签": {
            "场景标签": ["工作人员联系方式咨询"],
            "患者标签": [],
            "患者发言标签": ["咨询他人信息", "语气礼貌"],
            "回答标签": ["无法解答", "引导官方渠道咨询"],
            "补充标签": [],
        },
    },
    "additional_kwargs": {"refusal": None},
}

# 双层编码示例：content 是「JSON 字符串的 JSON 字符串」，一次解析得到 str
PAYLOAD_DOUBLE_ENCODED = {
    "role": "assistant",
    "content": json.dumps(
        '{"场景描述":"双层编码场景","患者提问":"双层编码提问","场景":"其它","子场景":"测试","场景置信度":0.9,"标签":{}}'
    ),
}


class TestAgentCreatorParseOutput(unittest.TestCase):
    """测试 agent_creator 输出解析逻辑（192-193 等价逻辑）。"""

    def test_untitled_1_string_content_one_level(self) -> None:
        """Untitled-1：content 为字符串，一层 JSON，应解析为 dict。"""
        payload = PAYLOAD_UNTITLED_1
        content = payload["content"]
        self.assertIsInstance(content, str, "本用例要求 content 为 str")

        result = content_to_edges_var_ready(content)
        self.assertIsInstance(result, dict, "应解析出 dict")
        self.assertIn("场景描述", result)
        self.assertIn("患者提问", result)
        self.assertEqual(result["场景"], "药物相关")
        self.assertEqual(result["子场景"], "药物替换咨询")

    def test_untitled_2_string_content_with_braces_in_value(self) -> None:
        """Untitled-2：content 为字符串，值内含 } 等字符，括号匹配应仍得到 dict。"""
        payload = PAYLOAD_UNTITLED_2
        content = payload["content"]
        self.assertIsInstance(content, str, "本用例要求 content 为 str")

        result = content_to_edges_var_ready(content)
        self.assertIsInstance(result, dict, "应解析出 dict")
        self.assertIn("场景描述", result)
        self.assertIn("患者提问", result)
        self.assertEqual(result["场景"], "记录血压")

    def test_untitled_3_dict_content(self) -> None:
        """Untitled-3：content 已为 dict，应直接返回。"""
        payload = PAYLOAD_UNTITLED_3
        content = payload["content"]
        self.assertIsInstance(content, dict, "本用例要求 content 为 dict")

        result = content_to_edges_var_ready(content)
        self.assertIsInstance(result, dict, "应得到 dict")
        self.assertEqual(result["场景描述"], content["场景描述"])
        self.assertEqual(result["场景"], "院内资源/政策咨询")

    def test_double_encoded_string_content(self) -> None:
        """content 为双层 JSON 编码字符串，第一次解析得到 str，第二次得到 dict。"""
        payload = PAYLOAD_DOUBLE_ENCODED
        content = payload["content"]
        self.assertIsInstance(content, str, "本用例 content 为 str")

        result = content_to_edges_var_ready(content)
        self.assertIsInstance(result, dict, "应解析出 dict")
        self.assertIn("场景描述", result)
        self.assertEqual(result["场景描述"], "双层编码场景")

    def test_parse_content_to_output_data_none_and_empty(self) -> None:
        """None、空串、非 str 非 dict 应返回 None。"""
        self.assertIsNone(parse_content_to_output_data(None))
        self.assertIsNone(parse_content_to_output_data(""))
        self.assertIsNone(parse_content_to_output_data("   "))
        self.assertIsNone(parse_content_to_output_data(123))


if __name__ == "__main__":
    unittest.main()
