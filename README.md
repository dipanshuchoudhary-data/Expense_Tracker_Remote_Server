# Expense_Tracker_Remote_Server

Expense Tracker Remote MCP Server

A production-style remote MCP (Model Context Protocol) server built with fastmcp, deployed on Google Cloud Run, and backed by Supabase for persistent storage.

This service is designed to be plugged into an external chatbot as a remote tool server, not as a standalone product.

It exposes MCP tools over SSE for:

Chat persistence

Conversation history

Expense-related operations

Future agent extensions

🚀 What This Service Does

This server acts as a remote capability layer for a chatbot.

Architecture:

Chatbot (local / hosted)
        ↓
Remote MCP Server (Cloud Run)
        ↓
Supabase (Postgres database)


Responsibilities:

Accept MCP connections over SSE

Expose structured tools to the chatbot

Persist and retrieve data from Supabase

Enforce safe startup and configuration

Run as a stateless, horizontally scalable service

🧩 Key Features

Remote MCP server using fastmcp

Cloud-native container deployment (Cloud Run)

Supabase-backed persistence

Environment-secured configuration

Designed for multi-user expansion

Compatible with agentic systems and tool calling

🛠 Tech Stack

Python 3.12

fastmcp

Supabase Python SDK

LangGraph

LangChain OpenAI (OpenRouter)

Docker

Google Cloud Run
