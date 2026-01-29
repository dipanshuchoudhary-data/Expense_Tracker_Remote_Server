from fastmcp import FastMCP
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph,START,END
from typing import TypedDict,List,Optional
from dotenv import load_dotenv
from supabase import create_client,Client
import uuid,os,logging

load_dotenv()
logging.basicConfig(level=logging.INFO)

SUPABASE_URL=os.getenv("SUPABASE_URL")
SUPABASE_KEY=os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing supabase env variables")

supabase: Client = create_client(SUPABASE_URL,SUPABASE_KEY)


model = ChatOpenAI(
    model_name="mistralai/mistral-7b-instruct",
    openai_api_base="https://openrouter.ai/api/v1",
    openai_api_key=os.getenv("OPENROUTER_API_KEY"),
    temperature=0.7
)

class ChatState(TypedDict):
    user_input:str
    messages:List[dict]
    thread_id:str



def save_messages(thread_id:str,role:str,content:str):
    supabase.table("chat_messages").insert({
        "thread_id":thread_id,
        "role":role,
        "content":content
    }).execute()

def load_history(thread_id:str):
    res = supabase.table("chat_messages")\
        .select("role,content")\
        .eq("thread_id",thread_id)\
        .order("created_at")\
        .execute()
    return res.data or []

def clear_thread(thread:str):
    supabase.table("chat.messages").delete().eq("thread_id",thread_id).execute()


def add_user_input(state: ChatState):
    state["messages"].append({"role": "user", "content": state["user_input"]})
    return state

def get_response(state: ChatState):
    try:
        reply = model.invoke(state["messages"]).content
    except Exception as e:
        logging.error(f"LLM error: {e}")
        reply = "System error. Please retry."

    save_message(state["thread_id"], "user", state["messages"][-1]["content"])
    save_message(state["thread_id"], "assistant", reply)

    state["messages"].append({"role": "assistant", "content": reply})
    return state

graph = StateGraph(ChatState)
graph.add_node("add_user_input",add_user_input)
graph.add_node("get_response",get_response)

graph.add_edge(START,"add_user_input")
graph.add_edge("add_user_input","get_response")
graph.add_edge("get_response",END)

workflow = graph.compile()


def chat_engine(user_input: str, thread_id: Optional[str] = None):
    if not thread_id:
        thread_id = str(uuid.uuid4())

    history = load_history(thread_id)

    state = {
        "user_input": user_input,
        "messages": history,
        "thread_id": thread_id
    }

    result = workflow.invoke(state)

    return {
        "thread_id": thread_id,
        "reply": result["messages"][-1]["content"]
    }

mcp = FastMCP("Expense_mcp_remote")

@mcp.tool()
def health():
    return {"status":"ok"}

@mcp.tool()
def chat(user_input:str,thread_id:Optional[str]= None):
    return chat_engine(user_input,thread_id)

@mcp.tool()
def history(thread_id: str):
    return load_history(thread_id)

@mcp.tool()
def clear(thread_id: str):
    clear_thread(thread_id)
    return {"cleared": thread_id}

# ---- intelligence tools ----

@mcp.tool()
def summarize(thread_id: str):
    history = load_history(thread_id)
    prompt = [{"role": "system", "content": "Summarize this conversation clearly."}] + history
    return {"summary": model.invoke(prompt).content}

@mcp.tool()
def extract_expenses(thread_id: str):
        history = load_history(thread_id)
        prompt = [{"role": "system", "content": "Extract expenses as structured JSON."}] + history
        return {"expenses": model.invoke(prompt).content}


if __name__ == "__main__":
    logging.info("Starting remote MCP server...")

    port = int(os.environ.get("PORT", 8080))

    mcp.run(
        transport="sse",
        host="0.0.0.0",
        port=port
    )


