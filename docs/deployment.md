# Deployment Guide

## 1. Deployment Goal

This project can be deployed as four services:

```text
MySQL 8.0
Redis Stack Server
Spring Boot e-commerce backend
FastAPI Agent service and chat frontend
```

Local demo target:

```text
http://localhost:8000          Chat page
http://localhost:8000/docs     Agent API docs
http://localhost:8080/api/doc.html  Java API docs
```

Production target:

```text
https://your-domain.com        Chat page and Agent API
https://api.your-domain.com    Java backend API, optional
```

## 2. Local Docker Deployment

### 2.1 Prerequisites

Install and start Docker Desktop.

You do not need to install these manually for the Docker demo:

- MySQL
- Redis
- Maven
- Python
- Java runtime

### 2.2 Start All Services

Run from the project root:

```powershell
docker compose up --build -d
```

If your local Docker installation uses standalone Compose, use:

```powershell
docker-compose up --build -d
```

Or use the helper script:

```powershell
.\start-demo.ps1
```

### 2.3 Check Service Status

```powershell
docker compose ps
```

Or:

```powershell
docker-compose ps
```

Expected services:

```text
redis
mysql
backend
agent
```

### 2.4 Open the Demo

```text
Chat page:       http://localhost:8000
Agent docs:      http://localhost:8000/docs
Java API docs:   http://localhost:8080/api/doc.html
```

Demo account:

```text
username: testuser
password: password
```

### 2.5 Stop Services

```powershell
docker compose down
```

Or:

```powershell
.\stop-demo.ps1
```

### 2.6 Reset Demo Data

Reset only the demo order data:

```powershell
.\reset-demo.ps1
```

Delete all container data and recreate MySQL seed data:

```powershell
docker compose down -v
docker compose up --build -d
```

## 3. Docker Compose Services

### 3.1 MySQL

Container image:

```text
mysql:8.0
```

Host port:

```text
3307 -> 3306
```

Initialization scripts:

```text
src/main/resources/sql/schema.sql
src/main/resources/sql/data.sql
```

Data volume:

```text
mysql-data
```

### 3.2 Redis

Container image:

```text
redis/redis-stack-server:latest
```

Data volume:

```text
redis-data
```

Used for:

- Conversation memory
- Structured conversation state
- Confirmation tokens
- LangGraph workflow checkpointer

### 3.3 Spring Boot Backend

Host port:

```text
8080 -> 8080
```

Important environment variables:

```dotenv
SPRING_PROFILES_ACTIVE=prod
DB_URL=jdbc:mysql://mysql:3306/ecommerce_db?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC
DB_USERNAME=root
DB_PASSWORD=123456
JWT_SECRET=change-this-in-production
```

### 3.4 FastAPI Agent

Host port:

```text
8000 -> 8000
```

Important environment variables:

```dotenv
AGENT_MODE=demo
ECOMMERCE_API_BASE_URL=http://backend:8080/api
REDIS_URL=redis://redis:6379/0
CONVERSATION_MAX_MESSAGES=12
CONVERSATION_TTL_SECONDS=1800
REQUEST_TIMEOUT_SECONDS=20
```

## 4. Environment Variables

Create `.env` from the example file:

```powershell
Copy-Item .env.docker.example .env
```

Recommended local demo configuration:

```dotenv
AGENT_MODE=demo
MYSQL_ROOT_PASSWORD=123456
JWT_SECRET=local-demo-jwt-secret-key-change-before-production-2026-at-least-64-bytes-long
BACKEND_HOST_PORT=8080
AGENT_HOST_PORT=8000
```

Recommended live model configuration:

```dotenv
AGENT_MODE=live
OPENAI_API_KEY=your-api-key
OPENAI_MODEL=gpt-5.4-mini
OPENAI_BASE_URL=
```

Never commit `.env` to Git.

## 5. Demo Mode vs Live Mode

| Mode | Model API Required | Usage |
| --- | --- | --- |
| `demo` | No | Stable local interview demo |
| `live` | Yes | Real LLM tool-calling behavior |
| `auto` | Optional | Use live when API key exists, otherwise demo |

For interviews, use `demo` first to avoid network or API-key issues. If the interviewer asks about real LLM integration, switch to `live` and explain the environment variables.

## 6. Local Verification

### 6.1 Verify Agent Health

```powershell
curl http://localhost:8000/health
```

Expected:

```json
{
  "status": "ok",
  "agent_mode": "demo"
}
```

### 6.2 Verify Login

```powershell
curl -X POST http://localhost:8000/auth/login `
  -H "Content-Type: application/json" `
  -d "{\"username\":\"testuser\",\"password\":\"password\"}"
```

### 6.3 Verify Chat

```powershell
curl -X POST http://localhost:8000/chat `
  -H "Content-Type: application/json" `
  -d "{\"message\":\"推荐 3000 元以内的手机\",\"session_id\":\"demo-session\"}"
```

### 6.4 Verify Streaming Chat

Use the browser chat page at:

```text
http://localhost:8000
```

Or use an API tool that supports event streams.

## 7. Run Tests

### 7.1 Java Tests

```powershell
.\mvnw.cmd test
```

### 7.2 Python Agent Tests

```powershell
cd agent-service
python -m pytest -q
```

If you use a virtual environment:

```powershell
cd agent-service
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
```

## 8. Cloud Server Deployment

### 8.1 Buy a Server

Recommended minimum configuration for demo:

```text
2 CPU
4 GB RAM
40 GB disk
Ubuntu 22.04 or 24.04
```

Open security group ports:

```text
22    SSH
80    HTTP
443   HTTPS
8000  Optional direct Agent access during debugging
8080  Optional direct Java access during debugging
```

For production, expose only `80` and `443`; keep `8000`, `8080`, `3307`, and Redis closed to the public internet.

### 8.2 Install Docker

On Ubuntu:

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

Log out and log in again, then check:

```bash
docker --version
docker compose version
```

### 8.3 Upload or Clone Project

```bash
git clone <your-repo-url>
cd ecommerce-order-system-memory
```

Create `.env`:

```bash
cp .env.docker.example .env
```

Edit secrets:

```bash
nano .env
```

At minimum, change:

```dotenv
MYSQL_ROOT_PASSWORD=change-this
JWT_SECRET=change-this-to-a-long-random-secret
AGENT_MODE=demo
```

### 8.4 Start Services

```bash
docker compose up --build -d
docker compose ps
```

Check logs:

```bash
docker compose logs -f backend
docker compose logs -f agent
```

## 9. Nginx Reverse Proxy

### 9.1 Install Nginx

```bash
sudo apt install -y nginx
```

### 9.2 Proxy Agent Service

Create:

```bash
sudo nano /etc/nginx/sites-available/ordermate.conf
```

Example config:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_buffering off;
        proxy_cache off;
    }
}
```

Enable:

```bash
sudo ln -s /etc/nginx/sites-available/ordermate.conf /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

Important for SSE:

- `proxy_buffering off`
- `proxy_cache off`
- Keep the Agent endpoint as streaming response with `text/event-stream`.

## 10. HTTPS

If you have a domain:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

Renewal check:

```bash
sudo certbot renew --dry-run
```

## 11. Production Checklist

Before exposing the service publicly:

- Change `MYSQL_ROOT_PASSWORD`.
- Change `JWT_SECRET` to a long random value.
- Do not expose MySQL or Redis ports publicly.
- Keep `.env` out of Git.
- Configure CORS origins explicitly.
- Use HTTPS.
- Use `AGENT_MODE=demo` for stable demos or configure a valid model key for `live`.
- Check Docker logs after every deployment.
- Backup MySQL data if real user data is stored.

## 12. Troubleshooting

### 12.1 Port Already in Use

Change ports in `.env`:

```dotenv
BACKEND_HOST_PORT=18080
AGENT_HOST_PORT=18000
```

Restart:

```powershell
docker compose up --build -d
```

Or:

```powershell
docker-compose up --build -d
```

### 12.2 MySQL Initialization Did Not Run

Docker only runs `/docker-entrypoint-initdb.d` scripts when the volume is empty.

Reset:

```powershell
docker compose down -v
docker compose up --build -d
```

If using standalone Compose:

```powershell
docker-compose down -v
docker-compose up --build -d
```

### 12.3 Agent Cannot Reach Java Backend

Inside Docker, Agent must use:

```text
http://backend:8080/api
```

Do not use `localhost:8080` inside the Agent container, because `localhost` means the Agent container itself.

### 12.4 Live Mode Reports Missing API Key

Either configure:

```dotenv
OPENAI_API_KEY=your-api-key
AGENT_MODE=live
```

Or switch back to:

```dotenv
AGENT_MODE=demo
```

### 12.5 SSE Works Locally but Not Behind Nginx

Check Nginx config:

```nginx
proxy_buffering off;
proxy_cache off;
```

Also check that the client is calling `/chat/stream`, not `/chat`.

### 12.6 Docker Daemon Is Not Running

If you see:

```text
failed to connect to the docker API at npipe:////./pipe/docker_engine
The system cannot find the file specified.
```

Docker Desktop is not running or has not finished starting.

Fix:

1. Open Docker Desktop.
2. Wait until Docker shows it is running.
3. Run:

```powershell
docker info
```

4. Start the project again:

```powershell
docker-compose up --build -d
```

### 12.7 `docker compose` Reports `unknown flag: --build`

Some Windows environments expose standalone Compose as `docker-compose.exe` instead of the Docker Compose v2 plugin.

Use:

```powershell
docker-compose up --build -d
```

## 13. Interview Explanation

You can explain deployment like this:

> I containerized the Java backend, FastAPI Agent service, MySQL, and Redis with Docker Compose. The Java backend owns transactional e-commerce data, while the Agent service handles conversation, tool orchestration, SSE streaming, and confirmation workflows. Redis stores short-term memory, structured conversation state, and confirmation tokens. For local interviews I use demo mode to avoid model API instability; for live mode I inject the model key through `.env`. In production I would put Nginx in front of the Agent service, enable HTTPS, and keep MySQL/Redis private.
