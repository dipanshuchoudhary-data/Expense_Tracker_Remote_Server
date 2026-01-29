Expense Tracker Remote MCP Server

A cloud-deployed remote MCP (Model Context Protocol) server built with fastmcp and backed by Supabase.
This service is designed to plug into an external chatbot as a remote capability layer, not as a standalone application.

It runs as a stateless microservice and exposes structured tools over SSE, enabling a chatbot to persist data, manage conversations, and perform expense-related operations through a secure, scalable backend.

🚀 What This Service Does

This server acts as a remote tool and memory service for a chatbot.

High-level architecture:

Chatbot (local or hosted)
        ↓
Remote MCP Server (Cloud Run)
        ↓
Supabase (PostgreSQL database)


Core responsibilities:

Accept MCP connections over SSE

Expose structured tools to the chatbot

Persist and retrieve data from Supabase

Enforce safe startup through environment validation

Run as a stateless, horizontally scalable service

🧩 Key Capabilities

Remote MCP server using fastmcp

Cloud-native container deployment

Supabase-backed persistence layer

Secure environment-based configuration

Designed for multi-user and agentic system expansion

Built to integrate cleanly with external chatbots

🛠 Tech Stack

Python 3.12

fastmcp (remote MCP server)

Supabase (PostgreSQL)

LangGraph

LangChain OpenAI (OpenRouter)

Docker

Google Cloud Run
