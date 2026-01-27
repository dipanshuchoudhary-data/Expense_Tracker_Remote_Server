from fastmcp import FastMCP
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph,START,END
from typing import TypedDict,List,Optional

import uuid,os
from dotenv import load_dotenv
from chat_store import save_message,load_chat_history
load_dotenv()



  
model = ChatOpenAI(
    model_name="mistralai/mistral-7b-instruct",
    openai_api_base="https://openrouter.ai/api/v1",
    openai_api_key=os.getenv("OPENROUTER_API_KEY"),
    temperature=1.0,
)

class ChatState(TypedDict):
    user_input:str
    messages:List[dict]
    thread_id:str

def add_user_input(state:ChatState):
    state["messages"].append(
        {"role":"user","content":state["user_input"]}
    )
    state["user_input"] = ""
    return state

async def get_response(state:ChatState):
    messages = state["messages"]
    thread_id = state["thread_id"]

    response = model.invoke(messages)
    assistant_msg = response.content

    await save_message(thread_id,"user",messages[-1]["content"])
    await save_message(thread_id,"assistant",assistant_msg)

    messages.append(
        {"role":"assistant","content":assistant_msg}
    )
    return state


graph = StateGraph(ChatState)
graph.add_node("add_user_input",add_user_input)
graph.add_node("get_response",get_response)

graph.add_edge(START,"add_user_input")
graph.add_edge("add_user_input","get_response")
graph.add_edge("get_response",END)

workflow = graph.compile()


async def chat_bot(user_input:str,thread_id:Optional[str]= None):
    if not thread_id:
        thread_id = str(uuid.uuid4())

    history = await load_chat_history(thread_id)

    state = {
        "user_input":user_input,
        "messages":history,
        "thread_id":thread_id,
    }

    result = await workflow.ainvoke(state)

    return {
        "thread_id": thread_id,
        "reply": result["messages"][-1]["content"],
        "messages": result["messages"],
    }