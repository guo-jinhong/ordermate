# E-commerce Customer Service Agent

FastAPI service that uses the OpenAI Responses API and function tools to query
the Spring Boot e-commerce backend.

## Current tools

- `search_products`
- `get_product_detail`
- `get_cart`
- `get_my_orders`
- `get_order_detail`
- `cancel_order`

`cancel_order` never executes during `/chat`. It creates a short-lived,
single-use confirmation token. The frontend must send that token to `/confirm`
with `approved=true` before the backend cancellation API is called.

## Run without MySQL

The service and its tests do not require MySQL. A database is only required when
you want tools to call the running Spring Boot backend with real data.

```powershell
cd agent-service
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest
uvicorn app.main:app --reload --port 8000
```

Copy `.env.example` to `.env` or set the environment variables in your shell.
The health endpoint works without an API key:

```text
GET http://localhost:8000/health
```

Without `OPENAI_API_KEY`, `AGENT_MODE=auto` selects the deterministic local demo
agent. Set `AGENT_MODE=live` and provide a key to use the real model.
Authenticated shopping-cart and order tools always require the JWT returned by
the Spring Boot login endpoint.

Interactive API documentation is available at:

```text
http://localhost:8000/docs
```

The browser demo is served by the same FastAPI process:

```text
http://localhost:8000/
```

It includes login, prompt shortcuts, tool-call traces, responsive layout, and a
server-backed confirmation card for destructive actions.

## Persistence

Without `REDIS_URL`, local development and the default Docker Compose stack use
bounded in-memory conversation history and confirmation stores.

Set `REDIS_URL` only when you want conversation history and confirmation tokens
to survive Agent service restarts. When Redis is configured, it also enables the
Redis-backed LangGraph checkpointer, so an interrupted confirmation workflow can
resume after an Agent restart.

For the Docker Compose and local full-stack demos, the Agent calls the Spring
Boot backend for product, cart, and order tools. The Spring Boot backend stores
those records in `ecommerce_db`.

The Agent also reads customer-service policy data from
`ecommerce_db.knowledge`. Use a restricted MySQL account such as `agent_user`
with `SELECT` permission on `knowledge` only, so the Agent cannot directly write
business tables. Business writes should continue to go through the backend API.

## MCP server

The project also provides a stdio MCP server with product search, product detail,
knowledge retrieval, authenticated order listing, and cancellation preflight.
The cancellation MCP tool never executes a write; it requires the user to confirm
through the OrderMate UI.

```powershell
python -m app.mcp_server
```
