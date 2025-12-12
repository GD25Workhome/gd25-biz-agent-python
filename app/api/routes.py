from fastapi import APIRouter, HTTPException
from app.schemas.chat import ChatRequest, ChatResponse
from domain.router.supervisor import create_workflow
from langchain_core.messages import HumanMessage

router = APIRouter()

# 初始化工作流
workflow = create_workflow()

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    聊天接口
    
    接收用户的消息，调用工作流处理，并返回响应。
    """
    try:
        # 准备状态
        state = {
            "messages": [HumanMessage(content=request.message)],
            "session_id": request.session_id,
            "user_id": request.user_id,
            "next_agent": None
        }
        
        # 调用工作流
        # 在实际应用中，我们会使用 checkpointer 来恢复状态
        final_state = await workflow.ainvoke(state)
        
        # 提取响应
        messages = final_state["messages"]
        last_message = messages[-1]
        
        return ChatResponse(
            response=last_message.content,
            metadata={"session_id": request.session_id}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
