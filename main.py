from fastmcp import FastMCP
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from typing import TypedDict, List, Optional
from dotenv import load_dotenv
from supabase import create_client, Client
import uuid, os, logging

load_dotenv()
logging.basicConfig(level=logging.INFO)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing supabase env variables")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ---------------------------------------------------------
# LLM
# ---------------------------------------------------------

model = ChatOpenAI(
    model_name="openai/gpt-oss-120b",
    openai_api_base="https://openrouter.ai/api/v1",
    openai_api_key=os.getenv("OPENROUTER_API_KEY"),
    temperature=0.7,
)


# ---------------------------------------------------------
# State
# ---------------------------------------------------------

class ChatState(TypedDict):
    user_input: str
    messages: List[dict]
    thread_id: str
    user_id: str


# ---------------------------------------------------------
# DB helpers (ALL USER SCOPED)
# ---------------------------------------------------------

def save_message(
    *,
    user_id: str,
    thread_id: str,
    role: str,
    content: str,
):
    if not user_id:
        raise RuntimeError("Unauthorized")

    supabase.table("chat_messages").insert({
        "user_id": user_id,
        "thread_id": thread_id,
        "role": role,
        "content": content,
    }).execute()


def load_history(
    *,
    user_id: str,
    thread_id: str,
):
    if not user_id:
        raise RuntimeError("Unauthorized")

    res = (
        supabase.table("chat_messages")
        .select("role,content")
        .eq("user_id", user_id)
        .eq("thread_id", thread_id)
        .order("created_at")
        .execute()
    )

    return res.data or []


def clear_thread(
    *,
    user_id: str,
    thread_id: str,
):
    if not user_id:
        raise RuntimeError("Unauthorized")

    supabase.table("chat_messages") \
        .delete() \
        .eq("user_id", user_id) \
        .eq("thread_id", thread_id) \
        .execute()


# ---------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------

def add_user_input(state: ChatState):
    state["messages"].append(
        {"role": "user", "content": state["user_input"]}
    )
    return state


def get_response(state: ChatState):
    try:
        reply = model.invoke(state["messages"]).content
    except Exception as e:
        logging.error(f"LLM error: {e}")
        reply = "System error. Please retry."

    save_message(
        user_id=state["user_id"],
        thread_id=state["thread_id"],
        role="user",
        content=state["messages"][-1]["content"],
    )

    save_message(
        user_id=state["user_id"],
        thread_id=state["thread_id"],
        role="assistant",
        content=reply,
    )

    state["messages"].append(
        {"role": "assistant", "content": reply}
    )

    return state


# ---------------------------------------------------------
# Graph
# ---------------------------------------------------------

graph = StateGraph(ChatState)
graph.add_node("add_user_input", add_user_input)
graph.add_node("get_response", get_response)

graph.add_edge(START, "add_user_input")
graph.add_edge("add_user_input", "get_response")
graph.add_edge("get_response", END)

workflow = graph.compile()


# ---------------------------------------------------------
# Engine
# ---------------------------------------------------------

def chat_engine(
    *,
    user_input: str,
    user_id: str,
    thread_id: Optional[str] = None,
):
    if not user_id:
        raise RuntimeError("Unauthorized")

    if not thread_id:
        thread_id = str(uuid.uuid4())

    history = load_history(
        user_id=user_id,
        thread_id=thread_id,
    )

    state: ChatState = {
        "user_input": user_input,
        "messages": history,
        "thread_id": thread_id,
        "user_id": user_id,
    }

    result = workflow.invoke(state)

    return {
        "thread_id": thread_id,
        "reply": result["messages"][-1]["content"],
    }


# ---------------------------------------------------------
# MCP server
# ---------------------------------------------------------

mcp = FastMCP("Expense_mcp_remote")


# ---------------------------------------------------------
# Health
# ---------------------------------------------------------

@mcp.tool()
def health():
    return {"status": "ok"}


# ---------------------------------------------------------
# Chat tools (ALL REQUIRE user_id)
# ---------------------------------------------------------

@mcp.tool()
def chat(
    user_input: str,
    user_id: str,
    thread_id: Optional[str] = None,
):
    return chat_engine(
        user_input=user_input,
        user_id=user_id,
        thread_id=thread_id,
    )


@mcp.tool()
def history(
    user_id: str,
    thread_id: str,
):
    return load_history(
        user_id=user_id,
        thread_id=thread_id,
    )


@mcp.tool()
def clear(
    user_id: str,
    thread_id: str,
):
    clear_thread(
        user_id=user_id,
        thread_id=thread_id,
    )
    return {"cleared": thread_id}


# ---------------------------------------------------------
# Intelligence tools (USER SCOPED)
# ---------------------------------------------------------

@mcp.tool()
def summarize(
    user_id: str,
    thread_id: str,
):
    history = load_history(
        user_id=user_id,
        thread_id=thread_id,
    )

    prompt = [
        {"role": "system", "content": "Summarize this conversation clearly."}
    ] + history

    return {
        "summary": model.invoke(prompt).content
    }


@mcp.tool()
def extract_expenses(
    user_id: str,
    thread_id: str,
):
    history = load_history(
        user_id=user_id,
        thread_id=thread_id,
    )

    prompt = [
        {"role": "system", "content": "Extract expenses as structured JSON."}
    ] + history

    return {
        "expenses": model.invoke(prompt).content
    }


# ---------------------------------------------------------
# Expense storage tool (MANDATORY user isolation)
# ---------------------------------------------------------

@mcp.tool()
async def add_expense(
    amount: float,
    category: str,
    user_id: str,
    description: Optional[str] = None,
    thread_id: Optional[str] = None,
):
    if not user_id:
        raise RuntimeError("Unauthorized")

    payload = {
        "user_id": user_id,
        "amount": amount,
        "category": category,
        "description": description,
        "thread_id": thread_id,
    }

    payload = {k: v for k, v in payload.items() if v is not None}

    result = supabase.table("expenses").insert(payload).execute()

    if not result.data:
        raise RuntimeError("Failed to insert expense")

    return {
        "status": "saved",
        "amount": amount,
        "category": category,
    }


# ---------------------------------------------------------
# Entry point
# ---------------------------------------------------------

if __name__ == "__main__":
    logging.info("Starting remote MCP server...")

    port = int(os.environ.get("PORT", 8080))

    mcp.run(
        transport="sse",
        host="0.0.0.0",
        port=port,
    )
