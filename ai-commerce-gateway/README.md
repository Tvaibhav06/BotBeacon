# AI Commerce Gateway

**Razorpay AI Buildathon · Track 01: AI Growth & Agentic Commerce**

> The infrastructure layer that makes a merchant ready for AI buyers.

## Quick Start

```bash
# Copy env and fill in your keys
cp backend/.env.example backend/.env

# One-command start (requires Docker + Docker Compose)
docker-compose up

# Or, run locally:
cd backend && python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
python -m app.db.seed
uvicorn app.main:app --reload --port 8000

cd ../frontend && npm install && npm run dev

# Buyer client (demo)
cd buyer-client && pip install -r requirements.txt
python scripted_buyer.py --intent "Find me running shoes under ₹6,000"
```

## Services

| Service   | URL                        |
|-----------|----------------------------|
| Backend   | http://localhost:8000      |
| Health    | http://localhost:8000/health |
| MCP       | http://localhost:8100/mcp  |
| Frontend  | http://localhost:5173      |
| Showcase  | http://localhost:5173/dev/components |

## Architecture

See [`docs/AI-Commerce-Gateway-Build-Plan.md`](docs/AI-Commerce-Gateway-Build-Plan.md) for the full technical spec.

**Safety invariant:** LLM proposes. Deterministic systems authorize. Razorpay executes.

The AI never has unrestricted access to payment execution. Every autonomous purchase must pass both Mandate Check and Policy Gate. If blocked, `razorpay_order_id = null` and Razorpay is never called.

## Project Structure

```
ai-commerce-gateway/
├── backend/       # Deterministic Gateway — FastAPI + PostgreSQL
├── buyer-client/  # AI Buyer — Gemini-backed, talks to Gateway via MCP only
├── frontend/      # Merchant Dashboard + Decision Receipt UI
└── docs/          # PRD, Build Plan, Project Idea
```
