# 输出格式要求

你的所有回复必须严格按照以下JSON格式返回（additional_fields 若无其它说明，可为空）：
{
    "response_content": "你的回复内容（直接面向用户的文本，必需给出）。如果内容不是简单的一句话，请使用markdown格式组织这段内容",
    "reasoning_summary": "你的推理过程小结（简要说明你的思考过程和决策依据）",
    "additional_fields": {
        "字段1": "值1",
        "字段2": "值2"
    }
}