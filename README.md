# BotBeacon — AI Commerce Gateway

> *The merchant-side infrastructure layer that makes online commerce discoverable, trustworthy, and transactable for autonomous AI buyers.*

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![Vite](https://img.shields.io/badge/Vite-6-646CFF?logo=vite&logoColor=white)](https://vitejs.dev)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![MCP](https://img.shields.io/badge/MCP-1.2.0%20(SSE)-7C3AED)](https://modelcontextprotocol.io)
[![Razorpay](https://img.shields.io/badge/Razorpay-Test%20Mode-0C2340?logo=razorpay&logoColor=white)](https://razorpay.com)
[![Tests](https://img.shields.io/badge/Tests-104%20Passing-brightgreen)](ai-commerce-gateway/backend/tests)

---

## 📌 The Problem & Solution

* **The Problem:** Modern e-commerce stores are engineered exclusively for human visual browsing. When an AI shopping assistant acts on a consumer's behalf (*"Find me running shoes under ₹6,000 and buy them"*), the merchant is invisible or untransactable. AI agents cannot safely reason over unstructured web pages, arbitrary pricing, unverified stock, or return policies.
* **The Solution:** **BotBeacon (AI Commerce Gateway)** converts existing merchant data into a structured **Commerce Passport**, exposes standardized tools over **Model Context Protocol (MCP)**, enforces deterministic spending mandates and merchant policy gates, and orchestrates test-mode **Razorpay** checkout with an immutable audit trail.

---

## 🛡️ Core Safety Invariant

$$\text{\bf LLM proposes. Deterministic systems authorize. Razorpay executes.}$$

* **No direct money access:** The AI agent never touches bank accounts, cards, or raw Razorpay payment execution APIs.
* **Dual-Gate Verification:**
  1. **Mandate Check (Buyer Authority):** Evaluates buyer spending limit, allowed merchandise categories, and expiration timestamp.
  2. **Policy Gate (Merchant Rules):** Deterministically evaluates stock availability, margin floors, discount ceilings, and approval thresholds.
* **Graceful Failure Guarantee:** If any mandate or policy check fails, transaction status becomes `blocked`, `razorpay_order_id = null`, and **Razorpay is never called**.
* **Zero Secret Leakage:** `RAZORPAY_KEY_SECRET` resides strictly in `backend/.env`. The frontend receives only the public `key_id`, and payment verification is conducted exclusively via server-side HMAC-SHA256 signature validation against Razorpay APIs.

---

## 🧾 Hero Feature: AI Commerce Decision Receipt

Every autonomous purchase outputs a transparent, explainable decision receipt showing the AI's step-by-step reasoning alongside deterministic guardrail confirmations:

### Scenario 1: Approved Purchase (Within Limits)
```
CUSTOMER INTENT
"Find me running shoes under ₹6,000"

AI CONSIDERED
18 products across catalog

SELECTED
Velocity Pro — ₹5,499 (Primary)
  ✓ Best match for running & performance
  ✓ In stock (40 units)
  ✓ Within ₹6,000 budget

UPSELL COMPLEMENT
Velocity Performance Socks — ₹499 (Complement)
  ✓ Highest-margin eligible accessory
  ✓ Total cart remains under ₹6,000 budget

FINAL CART
₹5,998 (Velocity Pro + Performance Socks)

GATES
  ✓ Mandate Check: Approved (₹5,998 <= ₹6,000 limit)
  ✓ Policy Gate: Approved (Margin floor & stock verified)

PAYMENT EXECUTION
  ✓ Razorpay Order Created: order_Q1a2b3c4d5
  ✓ Signature Verified: HMAC-SHA256 valid
  ✓ Status: approved_paid
```

### Scenario 2: Blocked Purchase (Budget Exceeded)
```
CUSTOMER INTENT
"Buy the 8999 Velocity Pro Premium footwear"

SELECTED
Velocity Pro (Premium) — ₹8,999

❌ DETERMINISTICALLY BLOCKED
  Buyer Mandate Limit: ₹6,000
  Requested Cart:     ₹8,999
  Reason:             Cart total ₹8,999 exceeds mandate limit ₹6,000

RESULT
  razorpay_order_id: null
  Razorpay was NEVER invoked. Zero money moved.
```

---

## 🏗️ Architecture & 5 Standardized MCP Tools

```
               MERCHANT
                  │
        Mode 1 Catalog & Rules
                  │
                  ▼
     ┌────────────────────────┐
     │  AI COMMERCE GATEWAY   │
     │  (FastAPI + Postgres)  │
     │  - Commerce Passport   │
     │  - Mandate Check       │
     │  - Policy Gate         │
     │  - Audit Trail         │
     └───────────┬────────────┘
                 │
                 │  Exposes 5 MCP Tools (/mcp)
                 ▼
     ┌────────────────────────┐
     │     AI BUYER CLIENT    │
     │   (Gemini 2.5 Flash)   │
     │  Reasons over intent,  │
     │  budget & complements  │
     └───────────┬────────────┘
                 │
       Calls Gateway via MCP:
       1. search_catalog
       2. get_product
       3. build_cart
       4. check_policy
       5. checkout
                 │
                 ▼
       ┌──────────────────┐
       │   POLICY CHECK   │
       └─────────┬────────┘
        APPROVED │    BLOCKED
                 │       └──▶ Explanation logged, Razorpay never called
                 ▼
       ┌──────────────────┐
       │     RAZORPAY     │  (ACP-style: CREATE → CONFIRM → COMPLETE)
       └─────────┬────────┘
                 ▼
       ┌──────────────────┐
       │   VERIFICATION   │  (Quoted vs. charged reconciliation)
       └─────────┬────────┘
                 ▼
       ┌──────────────────┐
       │ DECISION RECEIPT │  (Customer-facing reasoning + Audit Log)
       └──────────────────┘
```

### The 5 MCP Tools
1. `search_catalog` — Search products by category, tags, query, and maximum price.
2. `get_product` — Retrieve detailed SKU information, inventory status, and unit economics.
3. `build_cart` — Bundle primary item and complementary upsell within buyer constraints.
4. `check_policy` — Deterministic evaluation against merchant rules and buyer mandate.
5. `checkout` — Generates a Razorpay test-mode order only after policy approval.

---

## 🚀 Quick Start

### Prerequisites
* [Docker & Docker Compose](https://docs.docker.com/get-docker/) (Recommended) **OR**
* Local runtime: Python 3.11+, Node.js 18+, PostgreSQL 16+

---

### Option A: Docker Compose (Fastest)

1. Clone the repository and navigate to the project directory:
   ```bash
   cd ai-commerce-gateway
   ```

2. Copy the environment file and configure keys:
   ```bash
   cp backend/.env.example backend/.env
   ```
   *Add your `GEMINI_API_KEY`, `RAZORPAY_KEY_ID`, and `RAZORPAY_KEY_SECRET` in `backend/.env`.*

3. Start all services:
   ```bash
   docker-compose up --build
   ```

All containers will build, run Alembic migrations, and seed demo data automatically.

---

### Option B: Local Development (Step-by-Step)

#### 1. Configure Environment
```bash
cd ai-commerce-gateway/backend
cp .env.example .env
# Edit .env with your PostgreSQL credentials, Razorpay test keys, and Gemini API key
```

#### 2. Start Deterministic Gateway (Backend)
```bash
# From ai-commerce-gateway/backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
alembic upgrade head
python -m app.db.seed
uvicorn app.main:app --reload --port 8000
```

#### 3. Start Merchant Dashboard & Simulator (Frontend)
```bash
# In a new terminal
cd ai-commerce-gateway/frontend
npm install
npm run dev
```

#### 4. Run AI Buyer Client via CLI
```bash
# In a new terminal
cd ai-commerce-gateway/buyer-client
pip install -r requirements.txt

# Golden Path 1 (Approved):
python scripted_buyer.py --intent "Find me running shoes under 6000"

# Golden Path 2 (Blocked):
python scripted_buyer.py --intent "Buy the 8999 Velocity Pro Premium footwear"
```

---

## 🌐 Service Endpoints & Ports

| Service | Local Dev URL | Docker Compose URL | Description |
|---|---|---|---|
| **Frontend UI** | [http://localhost:5173](http://localhost:5173) | [http://localhost:5173](http://localhost:5173) | Merchant Dashboard & Live Simulator |
| **Backend API** | [http://localhost:8000](http://localhost:8000) | [http://localhost:8001](http://localhost:8001) | FastAPI Gateway & REST endpoints |
| **Health Check** | [http://localhost:8000/health](http://localhost:8000/health) | [http://localhost:8001/health](http://localhost:8001/health) | Gateway service health status |
| **MCP Server** | [http://localhost:8000/mcp](http://localhost:8000/mcp) | [http://localhost:8001/mcp](http://localhost:8001/mcp) | MCP Server mounted over SSE transport |
| **MCP Health** | [http://localhost:8000/mcp/health](http://localhost:8000/mcp/health) | [http://localhost:8001/mcp/health](http://localhost:8001/mcp/health) | Verifies 5 registered MCP tools |

---

## 🖥️ Merchant Dashboard Features

Log in with default seed credentials:
* **Email:** `admin@velocitysports.demo`
* **Password:** `demo1234`

| Page | Path | Key Capabilities |
|---|---|---|
| **Login** | `/login` | Secure JWT merchant authentication |
| **Onboarding Wizard** | `/onboarding` | 4-step Mode 1 catalog import, schema validation, and passport activation |
| **Commerce Passport** | `/passport` | Live structured merchant data viewer with JSON export |
| **Merchant Rules** | `/rules` | Minimum margin floor, max AI discount, upsell toggles, and approval thresholds |
| **Buyer Simulator** | `/simulator` | Real-time SSE live reasoning stream, decision engine visualizer, and Razorpay Checkout modal |
| **Transactions** | `/transactions` | Real-time transaction history with status badges (`approved_paid`, `blocked`, etc.) |
| **Audit Log** | `/audit` | Immutable cryptographic log of all passport, policy, payment, and verification events |
| **Decision Receipt** | `/receipt/:id` | Shareable customer-facing explainability view for any completed or blocked transaction |
| **Dev Components** | `/dev/components` | UI component design system showcase |

---

## 🧪 Testing & Verification

The project includes a comprehensive automated test suite covering all critical safety, policy, decision, checkout, and verification flows:

```bash
cd ai-commerce-gateway/backend
python -m pytest
```

### Test Coverage (104/104 Passing):
* **Checkout Safety (`test_checkout_safety.py`):** Asserts `checkout` independently checks `policy.approved`. If `False`, Razorpay is never instantiated and `razorpay_order_id = null`. Confirms `RAZORPAY_KEY_SECRET` is never exposed.
* **Mandate Enforcement (`test_mandate_check.py`):** Verifies buyer budget limits, expired mandates, and unauthorized product categories.
* **Policy Engine (`test_policy_gate.py`):** Tests out-of-stock blocking, margin floor protection, discount ceilings, and approval threshold rules.
* **Decision Engine (`test_decision_engine.py`):** Validates intent extraction, catalog ranking, price ceilings, and complementary upsell logic.
* **Data Validation (`test_validation.py`):** Validates catalog schema, negative pricing, and margin sanity checks before passport activation.
* **Post-Payment Verification (`test_verification.py`):** Reconciles quoted prices with charged amounts and verifies stock decrement.

---

## 📁 Repository Structure

```
BotBeacon/
├── README.md                                          # Project overview & documentation
├── AI-Commerce-Gateway-Build-Plan.md                 # Complete technical specification
├── prd.md                                             # Product Requirements Document
├── Project_idea.md                                    # Vision & architecture overview
├── ai-commerce-gateway-full-build-summary-phases-0-5.html
├── phase-6-complete-razorpay-checkout-verification.html
└── ai-commerce-gateway/                               # Primary Application Directory
    ├── docker-compose.yml                             # Container orchestration
    ├── backend/                                       # Deterministic Gateway
    │   ├── Dockerfile
    │   ├── requirements.txt
    │   ├── alembic/                                   # Database migrations
    │   ├── app/
    │   │   ├── main.py                                # FastAPI app & MCP mount
    │   │   ├── api/                                   # REST endpoints (merchants, rules, payments, audit)
    │   │   ├── core/                                  # Config, security, logging
    │   │   ├── db/                                    # Database session & seed script
    │   │   ├── mcp/                                   # MCP SSE server & 5 tool definitions
    │   │   ├── models/                                # SQLAlchemy ORM models
    │   │   └── services/                              # Policy gate, mandate check, Razorpay client
    │   └── tests/                                     # 104 automated unit & safety tests
    ├── buyer-client/                                  # AI Buyer Client (No backend imports)
    │   ├── requirements.txt
    │   ├── mcp_client.py                              # MCP SSE protocol client
    │   ├── gemini_client.py                           # Gemini 2.5 Flash reasoning client
    │   ├── decision_engine.py                         # Intent parsing, scoring & upsell logic
    │   └── scripted_buyer.py                          # CLI runner for approved & blocked demo paths
    └── frontend/                                      # Merchant Dashboard & Simulator
        ├── package.json
        ├── vite.config.ts
        ├── src/
        │   ├── App.tsx                                # React routing
        │   ├── components/                            # DecisionReceipt, DashboardLayout, etc.
        │   ├── design-system/                         # Reusable UI components
        │   ├── lib/                                   # API client, auth context, Razorpay hook
        │   └── pages/                                 # Simulator, Passport, Rules, Audit, etc.
```
