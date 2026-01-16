"""
将第一次提取的MD文件格式化为Excel格式
根据向量表字段：user_input, agent_response, tags, quality_grade
同时保留原始文档信息：source_file, original_content
"""
import re
import pandas as pd
from pathlib import Path
import json

# 输入和输出目录
INPUT_DIR = Path(__file__).parent.parent / "第一次提取"
OUTPUT_DIR = Path(__file__).parent

# 文件映射
FILE_MAPPING = {
    "01-QA类-健康咨询示例.md": "qa_examples",
    "02-Record类-数据记录示例.md": "record_examples",
    "03-Query类-数据查询示例.md": "query_examples",
    "04-Greeting类-问候示例.md": "greeting_examples",
}

# 默认质量等级
DEFAULT_QUALITY_GRADE = "良好"

def extract_qa_examples(content: str) -> list:
    """从QA类文件中提取问答示例"""
    examples = []
    
    # 提取场景标题和内容
    scene_pattern = r"### (.+?)\n\n(.*?)(?=###|$)"
    matches = re.finditer(scene_pattern, content, re.DOTALL)
    
    current_scene = None
    current_tags = []
    
    for match in matches:
        scene_title = match.group(1).strip()
        scene_content = match.group(2).strip()
        
        # 跳过标题部分
        if "数据来源" in scene_title or "提取说明" in scene_title:
            continue
            
        # 提取患者问题示例
        question_pattern = r"\*\*患者问题示例\*\*：\s*\n(.*?)(?=\*\*|$)"
        question_matches = re.finditer(question_pattern, scene_content, re.DOTALL)
        
        for q_match in question_matches:
            questions_text = q_match.group(1).strip()
            # 提取每行的问题
            questions = [q.strip().lstrip("- ").strip() for q in questions_text.split("\n") if q.strip() and q.strip().startswith("-")]
            
            # 提取回复话术
            reply_pattern = r"\*\*回复话术[^：]*\*\*：\s*\n(.*?)(?=\*\*|$)"
            reply_match = re.search(reply_pattern, scene_content, re.DOTALL)
            
            reply = ""
            if reply_match:
                reply = reply_match.group(1).strip()
                # 清理回复文本
                reply = re.sub(r'^\d+\.\s*', '', reply, flags=re.MULTILINE)  # 去除编号
                reply = re.sub(r'^-\s*', '', reply, flags=re.MULTILINE)  # 去除列表符号
                reply = re.sub(r'\n+', ' ', reply)  # 合并换行
                reply = reply.strip()
            
            # 为每个问题创建示例
            for question in questions:
                if question and reply:
                    # 构建tags
                    tags = [scene_title]
                    if "紧急" in scene_title or "危急" in scene_title:
                        tags.append("安全边界场景")
                    else:
                        tags.append("普通咨询")
                    
                    examples.append({
                        "user_input": question,
                        "agent_response": reply,
                        "tags": tags,
                        "quality_grade": DEFAULT_QUALITY_GRADE,
                        "source_file": "50-QA_agent.md",
                        "original_content": f"场景：{scene_title}\n问题：{question}\n回复：{reply}"
                    })
    
    return examples

def extract_record_examples(content: str) -> list:
    """从Record类文件中提取记录示例"""
    examples = []
    
    # 提取场景
    scene_pattern = r"### 场景：(.+?)\n\n.*?\*\*场景特征\*\*：(.*?)\n\n.*?\*\*用户输入示例\*\*：(.*?)\n\n.*?\*\*Agent回复示例\*\*：(.*?)(?=###|$)"
    matches = re.finditer(scene_pattern, content, re.DOTALL)
    
    for match in matches:
        scene_name = match.group(1).strip()
        scene_feature = match.group(2).strip()
        user_inputs_text = match.group(3).strip()
        agent_response = match.group(4).strip()
        
        # 提取用户输入列表
        user_inputs = [inp.strip().lstrip("- ").strip() for inp in user_inputs_text.split("\n") if inp.strip() and inp.strip().startswith("-")]
        
        # 清理回复
        agent_response = re.sub(r'^\d+\.\s*', '', agent_response, flags=re.MULTILINE)
        agent_response = re.sub(r'^-\s*', '', agent_response, flags=re.MULTILINE)
        agent_response = re.sub(r'\n+', ' ', agent_response)
        agent_response = agent_response.strip()
        
        # 构建tags
        tags = [scene_name]
        if "血压" in scene_name:
            tags.append("blood_pressure")
        elif "症状" in scene_name:
            tags.append("symptom")
        elif "用药" in scene_name:
            tags.append("medication")
        elif "健康事件" in scene_name:
            tags.append("health_event")
        
        # 为每个用户输入创建示例
        for user_input in user_inputs:
            if user_input and agent_response:
                examples.append({
                    "user_input": user_input,
                    "agent_response": agent_response,
                    "tags": tags,
                    "quality_grade": DEFAULT_QUALITY_GRADE,
                    "source_file": "10-blood_pressure_agent.md, 11-record_agent.md, 12-after_record_agent.md",
                    "original_content": f"场景：{scene_name}\n场景特征：{scene_feature}\n用户输入：{user_input}\n回复：{agent_response}"
                })
    
    return examples

def extract_query_examples(content: str) -> list:
    """从Query类文件中提取查询示例"""
    examples = []
    
    # 提取场景
    scene_pattern = r"### 场景：(.+?)\n\n.*?\*\*用户输入示例\*\*：(.*?)\n\n.*?\*\*Agent回复示例\*\*：(.*?)(?=###|$)"
    matches = re.finditer(scene_pattern, content, re.DOTALL)
    
    for match in matches:
        scene_name = match.group(1).strip()
        user_inputs_text = match.group(2).strip()
        agent_response = match.group(3).strip()
        
        # 提取用户输入列表
        user_inputs = [inp.strip().lstrip("- ").strip() for inp in user_inputs_text.split("\n") if inp.strip() and inp.strip().startswith("-")]
        
        # 清理回复
        agent_response = re.sub(r'^\d+\.\s*', '', agent_response, flags=re.MULTILINE)
        agent_response = re.sub(r'^-\s*', '', agent_response, flags=re.MULTILINE)
        agent_response = re.sub(r'\n+', ' ', agent_response)
        agent_response = agent_response.strip()
        
        # 构建tags
        tags = [scene_name]
        if "血压" in scene_name:
            tags.append("blood_pressure")
        elif "用药" in scene_name:
            tags.append("medication")
        elif "症状" in scene_name:
            tags.append("symptom")
        elif "健康事件" in scene_name:
            tags.append("health_event")
        
        # 为每个用户输入创建示例
        for user_input in user_inputs:
            if user_input and agent_response:
                examples.append({
                    "user_input": user_input,
                    "agent_response": agent_response,
                    "tags": tags,
                    "quality_grade": DEFAULT_QUALITY_GRADE,
                    "source_file": "20-query_agent.md",
                    "original_content": f"场景：{scene_name}\n用户输入：{user_input}\n回复：{agent_response}"
                })
    
    return examples

def extract_greeting_examples(content: str) -> list:
    """从Greeting类文件中提取问候示例"""
    examples = []
    
    # 提取场景
    scene_pattern = r"### 场景：(.+?)\n\n.*?\*\*用户输入示例\*\*：(.*?)\n\n.*?\*\*Agent回复示例\*\*：(.*?)(?=###|$)"
    matches = re.finditer(scene_pattern, content, re.DOTALL)
    
    for match in matches:
        scene_name = match.group(1).strip()
        user_inputs_text = match.group(2).strip()
        agent_response = match.group(3).strip()
        
        # 提取用户输入列表
        user_inputs = [inp.strip().lstrip("- ").strip() for inp in user_inputs_text.split("\n") if inp.strip() and inp.strip().startswith("-")]
        
        # 清理回复
        agent_response = re.sub(r'^\d+\.\s*', '', agent_response, flags=re.MULTILINE)
        agent_response = re.sub(r'^-\s*', '', agent_response, flags=re.MULTILINE)
        agent_response = re.sub(r'\n+', ' ', agent_response)
        agent_response = agent_response.strip()
        
        # 构建tags
        tags = [scene_name, "greeting"]
        
        # 为每个用户输入创建示例
        for user_input in user_inputs:
            if user_input and agent_response:
                examples.append({
                    "user_input": user_input,
                    "agent_response": agent_response,
                    "tags": tags,
                    "quality_grade": DEFAULT_QUALITY_GRADE,
                    "source_file": "00-intent_recognition_agent.md, 90-unclear-agent.md",
                    "original_content": f"场景：{scene_name}\n用户输入：{user_input}\n回复：{agent_response}"
                })
    
    return examples

def process_file(file_path: Path, file_type: str) -> list:
    """处理单个文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if file_type == "qa_examples":
        return extract_qa_examples(content)
    elif file_type == "record_examples":
        return extract_record_examples(content)
    elif file_type == "query_examples":
        return extract_query_examples(content)
    elif file_type == "greeting_examples":
        return extract_greeting_examples(content)
    else:
        return []

def main():
    """主函数"""
    print("开始格式化提取内容为Excel格式...")
    
    all_examples = {}
    
    # 处理每个文件
    for file_name, file_type in FILE_MAPPING.items():
        file_path = INPUT_DIR / file_name
        if not file_path.exists():
            print(f"警告：文件不存在 {file_path}")
            continue
        
        print(f"处理文件：{file_name}...")
        examples = process_file(file_path, file_type)
        all_examples[file_type] = examples
        print(f"  提取了 {len(examples)} 个示例")
    
    # 保存为Excel文件（每个Sheet一个类别）
    excel_path = OUTPUT_DIR / "提示词案例库.xlsx"
    with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
        for sheet_name, examples in all_examples.items():
            if examples:
                df = pd.DataFrame(examples)
                # 将tags列表转换为逗号分隔的字符串
                df['tags'] = df['tags'].apply(lambda x: ', '.join(x) if isinstance(x, list) else x)
                df.to_excel(writer, sheet_name=sheet_name, index=False)
                print(f"  保存到Sheet：{sheet_name} ({len(examples)} 条)")
    
    print(f"\n完成！Excel文件已保存到：{excel_path}")
    
    # 同时保存为JSON格式（便于查看）
    json_path = OUTPUT_DIR / "提示词案例库.json"
    json_data = {}
    for key, examples in all_examples.items():
        # 将tags列表转换为列表格式（JSON中保持列表）
        json_data[key] = examples
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    
    print(f"JSON文件已保存到：{json_path}")
    
    # 打印统计信息
    print("\n统计信息：")
    for sheet_name, examples in all_examples.items():
        print(f"  {sheet_name}: {len(examples)} 条")

if __name__ == "__main__":
    main()
