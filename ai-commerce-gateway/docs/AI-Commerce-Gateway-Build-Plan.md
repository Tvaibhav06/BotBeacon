# AI Commerce Gateway — Build Plan
**Razorpay AI Buildathon · Track 01: AI Growth & Agentic Commerce**

This document is the execution layer on top of `PRD.md` and `Project_idea.md`. Those two files are the "why" — read them for product rationale. This file is the "how": exact schemas, exact tool contracts, exact repo layout, exact design tokens, and a dependency-ordered ticket backlog. It is written to be handed directly to an AI coding agent (Claude Code / Codex) with minimal ambiguity left for the agent to guess at.

**Rule for the coding agent:** work phase by phase, in order, from §13. Do not skip ahead into a later phase's tools or fields. Do not add scope beyond §3. Where this document makes a judgment call the PRD didn't specify, it's flagged in §17 — if you hit a decision point not covered anywhere in this file, stop and ask rather than inventing new scope.

---

## Table of Contents
1. [Project Summary](#1-project-summary)
2. [Non-Negotiable Guardrails](#2-non-negotiable-guardrails)
3. [Tech Stack & Why](#3-tech-stack--why)
4. [Repository Structure](#4-repository-structure)
5. [Data Models](#5-data-models)
6. [MCP Tool Contracts](#6-mcp-tool-contracts)
7. [Backend REST API (Dashboard)](#7-backend-rest-api-dashboard)
8. [Core Logic Specs](#8-core-logic-specs)
9. [Frontend Design System](#9-frontend-design-system)
10. [Frontend Pages & Wireframes](#10-frontend-pages--wireframes)
11. [Demo Data / Seed Plan](#11-demo-data--seed-plan)
12. [Build Plan: Phased Ticket Checklist](#12-build-plan-phased-ticket-checklist)
13. [Environment & Run Commands](#13-environment--run-commands)
14. [Testing Strategy](#14-testing-strategy)
15. [Demo Script](#15-demo-script-3-minute-walkthrough)
16. [Assumptions & Open Questions](#16-assumptions--open-questions)

---

## 1. Project Summary

AI Commerce Gateway is a merchant-side infrastructure layer. A merchant's catalog, pricing, stock, and policies get structured into a **Commerce Passport**. The Passport is exposed to AI shopping agents through **5 MCP tools**. An AI buyer states intent ("find me running shoes under ₹6,000"), a **Decision Engine** picks a fit, a **Mandate Check** confirms the buyer agent is authorized to spend that much, a **Policy Gate** confirms the merchant's rules are satisfied, and only then does **Razorpay** get called, in test mode. Every step is written to an **Audit Log**. The output artifact a judge actually sees is the **AI Commerce Decision Receipt** — one for an approved purchase, one for a blocked one, side by side.

One sentence: *the layer that makes a merchant ready for AI buyers.*

## 2. Non-Negotiable Guardrails

**Building:**
- Commerce Passport (Mode 1 only — merchant-provided data)
- MCP tool layer (exactly 5 tools, see §6)
- A scripted AI buyer client that calls those tools
- Mandate Check + Policy Gate as two distinct, separately-testable gates
- Razorpay test-mode payment execution is called only on approval.
The checkout MCP tool may be invoked for both approved and blocked
decisions; blocked checkout produces a blocked TransactionResult without
calling Razorpay.
- Verification (quoted vs. charged/fulfilled)
- Append-only Audit Log
- The Decision Receipt UI (approved + blocked)
Clarification:
- Mandate limit = buyer-authorized spending boundary.
- approval_threshold_amount = merchant's threshold for requiring human approval,
  NOT a maximum sales/payment limit.
- The merchant can sell above the threshold; the AI simply cannot autonomously
  execute that transaction in MVP because no manual approval workflow exists.

**Not building (do not let scope drift here):**
- A general-purpose AI shopping chatbot
- A Google-like product search engine
- A universal web scraper / Mode 2 automatic website extraction
- Any path where an AI agent can spend money without passing both gates
- Per-field confidence scoring on merchant-provided data (Mode 1 merchant data is ground truth — only structural/range validation applies, see §8.5)
- A fully autonomous, free-form LLM buyer agent (the buyer client is **scripted**: it takes one intent string and drives a fixed sequence of tool calls — see §8.1 for exactly where the AI reasoning is and isn't)

**The one architectural fact that matters most:** the Gateway (backend) is deliberately deterministic. All LLM reasoning about *what to buy* lives in the buyer client, which talks to the Gateway **only** through the 5 MCP tools — never by importing Gateway code directly. This is what makes "any AI agent can plug in" a true claim instead of a marketing line, and it's the single easiest thing to accidentally violate under time pressure. See §4 and §8.1.

## 3. Tech Stack & Why

| Layer | Choice | Why |
|---|---|---|
| Backend | FastAPI (Python 3.11+) | Matches PRD's suggested stack; fast to iterate |
| Frontend | React + TypeScript + Vite + Tailwind | Matches PRD; Tailwind makes design tokens (§9) enforceable rather than aspirational |
| Database | PostgreSQL via SQLAlchemy + Alembic | You already have a working Postgres pattern (LowKey Secure) — reuse it instead of introducing SQLite just for hackathon convenience |
| Auth | JWT + a single `merchant_admin` role | Same shape as LowKey Secure (JWT/RBAC). MVP only needs one role — don't build multi-tenant RBAC you won't demo |
| LLM | Gemini | Two distinct uses, kept separate — see §8.1 and §8.5 |
| Payments | Razorpay Orders API, test mode | Required by the track |
| Agent protocol | MCP, **Streamable HTTP transport** (not stdio) | stdio requires spawning the server as a subprocess of one client; HTTP lets the Gateway run as a real, independently-reachable service — closer to how a real external AI agent would actually connect, and easier to demo live |
| Icons | lucide-react | Already available in this environment; consistent line-icon style matches the reference aesthetic (§9) |

Audit logging and auth patterns are a direct reuse of your **LowKey Secure** approach (React + JWT + RBAC + PostgreSQL + REST APIs) — same shape, applied here to merchant sessions and the append-only audit trail instead of whatever LowKey Secure originally protected.

## 4. Repository Structure

```
ai-commerce-gateway/
├── backend/                     # THE GATEWAY — deterministic infra only
│   ├── app/
│   │   ├── main.py
│   │   ├── core/                # config (pydantic-settings), security (JWT), logging
│   │   ├── models/               # SQLAlchemy models
│   │   ├── schemas/              # Pydantic schemas — see §5
│   │   ├── api/                  # REST for the merchant DASHBOARD (§7)
│   │   │   ├── merchants.py
│   │   │   ├── catalog.py
│   │   │   ├── rules.py
│   │   │   ├── transactions.py
│   │   │   ├── audit.py
│   │   ├── mcp/                  # the ONLY agent-facing surface
│   │   │   ├── server.py         # Streamable HTTP MCP server
│   │   │   └── tools/
│   │   │       ├── search_catalog.py
│   │   │       ├── get_product.py
│   │   │       ├── build_cart.py
│   │   │       ├── check_policy.py
│   │   │       └── checkout.py
│   │   ├── engine/                # deterministic checks ONLY — no LLM calls in this folder
│   │   │   ├── mandate_check.py
│   │   │   ├── policy_gate.py
│   │   │   └── verification.py
│   │   ├── integrations/
│   │   │   ├── razorpay_client.py
│   │   │   └── gemini_client.py   # catalog-structuring use only — see §8.5
│   │   ├── audit/
│   │   │   └── logger.py
│   │   └── db/
│   │       ├── session.py
│   │       └── seed.py            # §11
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
│
├── buyer-client/                 # THE AI BUYER — talks to backend ONLY via MCP tool calls
│   ├── decision_engine.py        # Gemini-backed intent parsing + fit scoring + upsell — §8.1
│   ├── mcp_client.py             # thin wrapper calling the 5 tools over HTTP
│   ├── scripted_buyer.py         # demo entrypoint: one intent string in, receipt out
│   └── requirements.txt
│
├── frontend/                     # merchant dashboard + Decision Receipt UI
│   ├── src/
│   │   ├── main.tsx / App.tsx
│   │   ├── pages/                 # §10
│   │   ├── components/
│   │   ├── design-system/         # tokens, Button, Card, Badge, StatusPill — §9
│   │   └── lib/api.ts
│   ├── tailwind.config.ts
│   └── package.json
│
├── docs/
│   ├── PRD.md
│   ├── Project_idea.md
│   └── AI-Commerce-Gateway-Build-Plan.md   # this file
│
├── docker-compose.yml            # Postgres + backend + frontend, one command for judges
└── README.md
```

The `backend/` ↔ `buyer-client/` split is a hard boundary, not a suggestion. If a ticket in §12 seems easier to implement by having `buyer-client/` import something from `backend/app/`, that's a signal the ticket is being done wrong.

## 5. Data Models

Pydantic schemas (mirror as SQLAlchemy models where persisted). Field names below are the ones every other section of this document uses — keep them exact so the MCP contracts, REST routes, and seed data all line up without translation.

```python
class Product(BaseModel):
    id: str                              # "prod_001"
    name: str
    category: str                        # "footwear" | "accessories" | ...
    tags: list[str] = []                 # ["running", "men"]
    price: float                         # INR, merchant sale price
    cost: float                          # merchant cost basis — margin checks only, never shown to buyer
    stock: int
    complement_categories: list[str] = []  # e.g. shoes -> ["accessories"], drives upsell matching
    description: str = ""
    image_url: str | None = None
    status: Literal["active", "inactive"] = "active"

class MerchantRules(BaseModel):
    max_ai_discount_pct: float = 0
    upsell_enabled: bool = True
    preferred_categories: list[str] = []
    min_margin_pct: float = 10           # (price - cost) / price, as a percentage
    approval_threshold_amount: float | None = None   # Above this amount, AI requires merchant approval before checkout; not a sales/payment ceiling

class Merchant(BaseModel):
    id: str
    name: str
    rules: MerchantRules
    passport_status: Literal["draft", "active"] = "draft"

class ValidationIssue(BaseModel):
    product_id: str
    field: str
    message: str
    severity: Literal["error", "warning"]  # error blocks activation, warning does not — see §8.5

class Mandate(BaseModel):
    id: str
    buyer_id: str
    max_amount: float
    category_scope: list[str] = []       # empty list = unscoped (any category)
    expires_at: datetime

class CartItem(BaseModel):
    product_id: str
    quantity: int
    unit_price: float                    # SNAPSHOT at build_cart time — this is what Verification checks against
    role: Literal["primary", "upsell"] = "primary"

class Cart(BaseModel):
    id: str
    merchant_id: str
    buyer_id: str
    items: list[CartItem]
    total: float

class MandateCheckResult(BaseModel):
    passed: bool
    reasons: list[str]

class PolicyCheckResult(BaseModel):
    passed: bool
    reasons: list[str]

class PolicyDecision(BaseModel):
    id: str
    cart_id: str
    mandate_check: MandateCheckResult
    policy_check: PolicyCheckResult
    approved: bool                       # true only if BOTH sub-checks passed
    reasons: list[str]                   # merged, human-readable

class TransactionResult(BaseModel):
    id: str
    cart_id: str
    razorpay_order_id: str | None        # MUST be None when status == "blocked"
    status: Literal["approved_paid", "blocked", "failed"]
    amount: float

class VerificationResult(BaseModel):
    transaction_id: str
    match: bool
    discrepancies: list[str]

class AuditLogEntry(BaseModel):
    id: str
    timestamp: datetime
    merchant_id: str
    transaction_id: str | None
    stage: Literal["passport_activated", "decision_engine", "mandate_check",
                    "policy_gate", "payment", "verification"]
    actor: Literal["system", "buyer_agent", "merchant"]
    payload: dict
    result: dict

class DecisionReceipt(BaseModel):
    transaction_id: str
    customer_request: str
    ai_considered_count: int | None
    selected: CartItem | None
    why: list[str] = []
    upsell: CartItem | None
    final_total: float
    authorization_status: str            # e.g. "Within buyer limit" / "Blocked — exceeds buyer limit"
    payment_status: str                  # e.g. "Razorpay verified" / "Razorpay was never called"
```

## 6. MCP Tool Contracts

Exactly 5 tools, no more. Every field name matches §5.

### `search_catalog`
Deterministic. No LLM. Category / keyword / price filtering only.
```json
// input
{ "query": "running shoes", "max_price": 6000, "category": "footwear", "limit": 20 }
// output
{ "products": [ {"id": "...", "name": "...", "category": "...", "price": 0, "stock": 0, "tags": []} ],
  "considered_count": 18 }
```

### `get_product`
```json
// input:  { "product_id": "prod_001" }
// output: full Product object (§5)
```

### `build_cart`
Snapshots prices at call time into `CartItem.unit_price` — this snapshot is what Verification later checks against.
```json
// input
{ "buyer_id": "demo-buyer-1", "items": [ {"product_id": "prod_001", "quantity": 1, "role": "primary"},
                                          {"product_id": "prod_006", "quantity": 1, "role": "upsell"} ] }
// output: full Cart object (§5)
```

### `check_policy`
Accepts either a stored `mandate_id` (resolved server-side against the seeded Mandate table) or an inline `mandate` object for testing. Runs Mandate Check + Policy Gate (§8.2, §8.3) and returns the combined decision.
```json
// input
{ "cart_id": "cart_abc", "mandate_id": "mandate_demo_buyer_1" }
// output: full PolicyDecision object (§5)
```

### `checkout`
```json
// input:  { "cart_id": "cart_abc", "policy_decision_id": "pd_123" }
// output: full TransactionResult object (§5)
```

**Hard rule, unit-tested (§14):** `checkout` re-checks `policy_decision.approved == true` itself, immediately before touching the Razorpay client. It does not trust that the caller already checked. If `approved == false`, it returns `status: "blocked"` with `razorpay_order_id: null` and the Razorpay client is never instantiated. This single check is what makes "Razorpay was never called" a true statement instead of a UI-only claim.

## 7. Backend REST API (Dashboard)

Separate from the MCP tools above — this is what the React dashboard calls, not what an AI agent calls.

| Method & Path | Purpose |
|---|---|
| `POST /api/merchants/onboard` | Create merchant |
| `POST /api/merchants/{id}/catalog/upload` | CSV upload |
| `POST /api/merchants/{id}/catalog` | Manual add/edit one product |
| `GET /api/merchants/{id}/passport` | Products + validation issues + status |
| `POST /api/merchants/{id}/passport/activate` | Runs validation, sets `passport_status = active` if no `error`-severity issues |
| `POST /api/merchants/{id}/rules` | Save `MerchantRules` |
| `GET /api/merchants/{id}/transactions` | List, for dashboard |
| `GET /api/transactions/{id}/receipt` | `DecisionReceipt` for one transaction |
| `GET /api/transactions/{id}/audit-trail` | Every `AuditLogEntry` for that transaction, in order |
| `GET /api/merchants/{id}/audit-log` | Raw log, filterable by `stage` |
| `POST /api/demo/buyer-request` | Dashboard "Run" button — invokes `buyer-client/scripted_buyer.py` with the given intent string and streams back the flow stages + final receipt. This is what powers §10's Buyer Simulator page |

## 8. Core Logic Specs

### 8.1 Decision Engine — lives in `buyer-client/`, NOT in `backend/`
This is the one place genuine LLM reasoning happens about *what to buy*. Steps:
1. Gemini: intent string → structured filter `{category, max_price, keywords}`
2. Call MCP `search_catalog` with that filter (deterministic, Gateway-side)
3. Hybrid scoring:
   deterministic pre-filter on budget/stock/category first, then score
   remaining candidates using:
   - buyer intent / keyword and tag fit
   - product suitability
   - availability
   - merchant preferred_categories as a ranking preference
   - optionally merchant economics

   Merchant preferences may influence ranking only; they must never
   override buyer mandate constraints or hard eligibility rules.
4. If `rules.upsell_enabled` and the mandate has headroom left after the primary item, pick the highest-price in-budget product whose `category` is in the selected item's `complement_categories`.
5. Call MCP build_cart, then check_policy, then checkout. checkout() must be invoked for both approved and blocked decisions. For a blocked decision, checkout() creates a blocked TransactionResult but MUST NOT instantiate or call the Razorpay client.
6. Assemble the `DecisionReceipt` from the results for display.

### 8.2 Mandate Check — `backend/app/engine/mandate_check.py`
```
passed = (cart.total <= mandate.max_amount)
      AND (mandate.category_scope is empty OR every cart item's category ⊆ mandate.category_scope)
      AND (now < mandate.expires_at)
```
Each failed condition appends a specific reason string, e.g. `"exceeds buyer limit (₹8,999 > ₹6,000)"`.

### 8.3 Policy Gate — `backend/app/engine/policy_gate.py`
Deterministic merchant-side checks, re-run at gate time (don't trust `build_cart`'s snapshot for stock — check live):
- **Stock:** every item's `quantity <= live stock`
- **Margin floor:** every item's `(price - cost) / price * 100 >= rules.min_margin_pct`
- **Discount limit:** any applied discount `% > rules.max_ai_discount_pct` → fail
- **Autonomous approval threshold:** if `cart.total > rules.approval_threshold_amount`, BLOCK the autonomous transaction with reason `"merchant approval required for autonomous purchase"`. This is an autonomy boundary, not a maximum sales/payment limit.

`PolicyDecision.approved = mandate_check.passed AND policy_check.passed`.
### 8.4 Razorpay Checkout + Verification

Checkout follows an ACP-shaped three-stage lifecycle:

**CREATE**
→ `checkout` creates a Razorpay test-mode Order after both Mandate Check and Policy Gate have approved the cart.

**CONFIRM**
→ The frontend opens the real Razorpay Checkout.js modal using the created `order_id`; the test buyer confirms the payment.

**COMPLETE**
→ The server verifies the Razorpay payment/signature and amount, runs cart/stock verification, and records the final transaction state.

Before marking a payment as verified:

1. Perform server-side Razorpay signature verification.
2. Verify the payment/order relationship.
3. Verify the charged amount against the approved cart total.
4. Run cart/stock verification against the approved cart.
5. Mark the transaction as verified only if all required checks pass.

If any verification check fails, log the discrepancy and keep the transaction visible with a failed/mismatch status — never silently accept the payment.

For a blocked decision, `checkout` returns a `blocked` `TransactionResult` without creating a Razorpay Order or calling the Razorpay client.

### 8.5 Audit Log — write incrementally, don't bolt on later
Every stage in `AuditLogEntry.stage` gets written as it happens, starting in Phase 1 (`passport_activated`) through Phase 6 (`verification`). §12's Phase 7 is a completeness *pass*, not new logging code.

### 8.6 Mode 1 Validation (Commerce Passport)
Merchant data is ground truth — **no confidence scoring**. Only structural/range checks, each tagged `error` (blocks activation) or `warning` (flagged, does not block):
- `error`: missing required field, `price <= 0`, `stock < 0`
- `warning`: `price < cost * (1 + min_margin_pct/100)` — i.e. priced under the merchant's own stated minimum margin

Optional, lower priority: Gemini can assist mapping arbitrary CSV column headers onto the `Product` schema during upload (this is the only Gateway-side Gemini use — data *structuring*, not purchasing *decisions*, and it's reviewed by the merchant before activation either way).

## 9. Frontend Design System

Your reference screenshot is a bold black/white/lime marketing template — colors sampled directly from your uploaded image, not guessed:

| Token | Hex | Sampled from |
|---|---|---|
| `--ink` | `#191A23` | dark navy pill buttons / dark cards |
| `--lime` | `#B9FF66` | accent cards, the color the whole system should read as "approved" |
| `--white` | `#FFFFFF` | primary background |
| `--surface` | `#F3F3F3` | secondary/alternating section background |
| `--border` | `#DADADB` | card borders, dividers |
| `--coral` (derived, not sampled) | `#FF6B57` | the *only* other saturated color in the palette — reserved for BLOCK states. Don't reach for a generic Tailwind red |

**Type:** two families, clearly distinct roles (not the generic default pairing) —
- **Space Grotesk** for headings, page titles, the Decision Receipt's numbers — carries the geometric personality of the reference
- **Inter** for body copy, table data, form labels — a workhorse face for dense dashboard content, where Space Grotesk would hurt legibility at small sizes

**Layout principles:**
- Big radius on cards (~16–20px), pill-shaped buttons (`border-radius: 999px`) — carried directly from the reference
- Alternate white and `--surface` sections the way the reference alternates white and dark blocks, but for a *dashboard* that means alternating table zebra-striping and card backgrounds, not literal marketing-page section blocks
- The Decision Receipt is the one place to spend real visual boldness: dark `--ink` card, lime checkmarks for an approved reason, coral for a blocked one, oversized numerals for the final total — see §10.2. Keep every other screen (catalog table, rules form, audit log) quiet and functional so the Receipt actually reads as the hero moment
- Icons: lucide-react, one consistent stroke weight, no filled/glossy icons

**A note on the palette, for transparency:** black-navy + a single acid-lime accent is *also* one of the color combinations generic AI design tools default to when given no direction. Since you've pinned it explicitly with a reference image, that's a real brief choice, not a fallback — keep it. The thing that will actually determine whether this reads as "designed for this product" versus "templated" is everything *else*: grounding layout in real dashboard content (tables, forms, a receipt) rather than marketing-page patterns, and avoiding the unrelated tells below.

**Explicitly avoid** (none of these come from your reference; don't let a coding agent default into them):
- Identical rounded cards everywhere with the same soft `rgba(0,0,0,.1)` shadow regardless of hierarchy
- A literal `→` character appended to button/link text
- Tracked-out ALL-CAPS eyebrow labels above every section heading (the Decision Receipt's own field labels — `CUSTOMER REQUEST`, `AI CONSIDERED`, etc. — are the one exception: that capitalization is literally specified in the PRD's own example receipt, kept verbatim as receipt/boarding-pass convention, not decorative chrome)
- Numbered `01 / 02 / 03` markers on anything that isn't a genuine sequence (the onboarding wizard in §10.1 *is* a genuine sequence — numbering it is fine)
- Gradient washes as pure decoration

## 10. Frontend Pages & Wireframes

### 10.1 Information architecture
```
Sidebar (--ink background, --white active-item text on a --lime pill)
├── Passport & Catalog
├── Rules
├── Buyer Simulator   ← the demo page
├── Transactions
└── Audit Log
```
Onboarding is a separate 4-step wizard, numbered (Connect/Upload → Review & Validate → Configure Rules → Activate) — a real sequence, so numbering is correct here.

### 10.2 Decision Receipt component
```
┌───────────────────────────────────────────┐   dark --ink card
│  AI COMMERCE DECISION RECEIPT              │
│                                             │
│  Request                                   │
│  "Find me running shoes under ₹6,000"      │
│                                             │
│  Considered            18 products         │
│  Selected              Velocity Pro        │
│                         ₹5,499             │
│                                             │
│  Why                                       │
│  ✓ Best fit for intent          } lime      │
│  ✓ In stock                     } checks    │
│  ✓ Within budget                 }          │
│                                             │
│  Upsell — Socks — ₹499                     │
│  Highest-value eligible complement         │
│  ───────────────────────────               │
│  Final                          ₹5,998     │  ← oversized numeral
│                                             │
│  Authorization      ✓ Within buyer limit   │
│  Payment            ✓ Razorpay verified    │
└───────────────────────────────────────────┘
```
Blocked variant: use the same visual language but render a deliberately
shorter receipt focused on the request, block reason, buyer limit,
requested amount, and the closing statement:

"Razorpay was never called."

Do not render AI_CONSIDERED, SELECTED, WHY, or UPSELL when the transaction
is blocked unless those fields are explicitly available and useful.

### 10.3 Buyer Simulator page
```
┌─────────────────────────────┬───────────────────────────┐
│ Mandate: Demo Buyer          │                            │
│  max ₹6,000 · footwear+acc.  │   Decision Receipt renders │
│                               │   here after Run           │
│ Try a request                │                            │
│ ┌───────────────────────┐    │                            │
│ │ Find me running shoes  │    │                            │
│ │ under ₹6,000           │    │                            │
│ └───────────────────────┘    │                            │
│ [ Run ]                      │                            │
│                               │                            │
│ Presets:                     │                            │
│  • Running shoes under 6k    │                            │
│  • Buy the ₹8,999 version    │                            │
│                               │                            │
│ Flow                          │                            │
│  ● Decision Engine            │                            │
│  ● Mandate Check               │                            │
│  ● Policy Gate                  │                            │
│  ● Razorpay                      │                            │
│  ● Verification                   │                            │
└─────────────────────────────┴───────────────────────────┘
```
Each `Flow` stage lights up (lime = passed, coral = failed/stopped-here) as `POST /api/demo/buyer-request` streams progress — this live progression IS the demo; don't just show a spinner and then the final receipt.

## 11. Demo Data / Seed Plan

Merchant: **Velocity Sports**. Rules: `max_ai_discount_pct=10`, `upsell_enabled=true`, `preferred_categories=["footwear","accessories"]`, `min_margin_pct=15`, `approval_threshold_amount=15000`.     # AI can sell above ₹15,000 only with merchant approval. It is NOT a maximum transaction amount.
Mandate: `id=mandate_demo_buyer_1`, `buyer_id=demo-buyer-1`, `max_amount=6000`, `category_scope=["footwear","accessories"]`, `expires_at = now + 30d`.

Seed products (script generates ~10 more filler SKUs across the same two categories to realistically reach "AI considered 18 products"):

| id | name | category | price | cost | stock | complement_categories |
|---|---|---|---|---|---|---|
| prod_001 | Velocity Pro | footwear | 5499 | 3200 | 40 | [accessories] |
| prod_002 | Velocity Pro (Premium) | footwear | 8999 | 5200 | 15 | [accessories] |
| prod_003 | Trail Runner X | footwear | 4999 | 2800 | 25 | [accessories] |
| prod_004 | Court Classic | footwear | 3499 | 1900 | 60 | [accessories] |
| prod_005 | Everyday Sneaker | footwear | 2999 | 1600 | 80 | [accessories] |
| prod_006 | Performance Socks (2-pack) | accessories | 499 | 220 | 200 | [] |
| prod_007 | Cushion Insoles | accessories | 699 | 300 | 90 | [] |
| prod_008 | Running Cap | accessories | 599 | 260 | 70 | [] |

Two demo requests (drive §15 directly from these):
1. `"Find me running shoes under ₹6,000"` → `prod_001` + `prod_006` upsell → APPROVE, ₹5,998 total
2. `"Buy the ₹8,999 version instead"` → `prod_002` alone → BLOCK, exceeds ₹6,000 mandate

## 12. Build Plan: Phased Ticket Checklist

Each phase maps back to the PRD's own build order (noted in brackets) but is broken into independently-testable tickets with a concrete Definition of Done.

### Phase 0 — Scaffolding & Design System Setup
- [ ] Monorepo per §4; FastAPI skeleton; SQLAlchemy + Alembic against Postgres
- [ ] Vite + React + TS + Tailwind; install `lucide-react`
- [ ] Tailwind theme configured with §9's tokens (colors, `Space Grotesk`/`Inter`, radius scale) — no default Tailwind indigo/purple left reachable
- [ ] `docker-compose.yml`: Postgres + backend + frontend
- [ ] A `/dev/components` showcase page rendering Button/Card/Badge/StatusPill in the real palette, for visual QA before real pages exist
- **DoD:** `docker-compose up` boots an empty shell; health-check endpoint responds; showcase page visibly uses `--ink`/`--lime`, not default Tailwind colors.

### Phase 1 — Commerce Passport `[PRD #1]`
- [ ] `Merchant`, `Product`, `MerchantRules` models + schemas (§5)
- [ ] `POST /api/merchants/onboard`, catalog upload (CSV) + manual add
- [ ] Validation per §8.6 (error vs. warning severity)
- [ ] `GET /api/merchants/{id}/passport`, `POST .../passport/activate`
- [ ] Seed script (§11)
- [ ] Frontend: 4-step onboarding wizard; Catalog page with validation badges
- **DoD:** seeding produces an ACTIVE passport; a product with `price=0` blocks activation; a product priced under margin shows a warning but doesn't block it.

### Phase 2 — MCP Tool Layer + Buyer Client Plumbing `[PRD #2]`
- [ ] MCP server (Streamable HTTP) exposing all 5 tools, backed by Phase 1 data
- [ ] `search_catalog`, `get_product`, `build_cart` per §6 — deterministic, no LLM
- [ ] `buyer-client/scripted_buyer.py` with a hardcoded naive selection (e.g. cheapest in-budget match) — just prove the wire works
- [ ] `check_policy`/`checkout` stubbed to always approve, but the "no Razorpay unless approved" rule (§6) is enforced from day one, not added later
- **DoD:** running `scripted_buyer.py` with a hardcoded request produces a completed (stubbed) transaction end-to-end over real MCP HTTP calls — no direct backend imports from `buyer-client/`.

### Phase 3 — Decision Engine (Gemini, buyer-side)
- [ ] Intent → structured filter via Gemini
- [ ] Hybrid fit scoring + "why" bullet generation (§8.1)
- [ ] Upsell selection from `complement_categories` + `rules.upsell_enabled` + remaining mandate headroom
- [ ] `considered_count` threaded through to the eventual receipt
- **DoD:** the real string `"Find me running shoes under ₹6,000"` against the seeded catalog selects `prod_001` + `prod_006` — matching §11's numbers exactly.

### Phase 4 — Mandate Check `[PRD #3]`
- [ ] `Mandate` model + seed
- [ ] `mandate_check()` per §8.2
- [ ] Wired into `check_policy` (accepts `mandate_id` or inline `mandate`)
- **DoD:** cart total ₹5,998 → passes; `prod_002` alone (₹8,999) → fails with the exact reason string from §8.2's example.

### Phase 5 — Merchant Rules + Policy Gate `[PRD #4]`
- [ ] Rules config form + `POST /api/merchants/{id}/rules`
- [ ] `policy_gate()` per §8.3 (stock, margin, discount, approval threshold)
- [ ] Combine into one persisted `PolicyDecision`, returned from `check_policy`
- **DoD:** both §11 demo requests produce APPROVE/BLOCK purely from real rule evaluation — outcome is never hardcoded.

### Phase 6 — Razorpay Checkout + Verification `[PRD #5]`
- [ ] Razorpay test-mode client: create Order
- [ ] Frontend: real Checkout.js modal wired to an APPROVEd Buyer Simulator run
- [ ] `checkout` tool re-verifies `approved==true` immediately before calling Razorpay (unit-tested — §14)
- [ ] Payment success callback marks the transaction paid
- [ ] `verification()` per §8.4
- [ ] Server-side Razorpay payment/signature verification before marking the transaction as verified
- **DoD:** paying with test card `4111 1111 1111 1111` produces a paid transaction + a `match=True` Verification log; a manually-edited price between cart-build and payment produces a logged discrepancy, not a silent success.

### Phase 7 — Audit Log completeness pass `[PRD #6, built incrementally since Phase 1]`
- [ ] Confirm every `stage` in §5's `AuditLogEntry` is actually written somewhere already — this is an audit of existing code, not new logging
- [ ] `GET /api/merchants/{id}/audit-log`, `GET /api/transactions/{id}/audit-trail`
- [ ] Frontend: Audit Log page + a per-transaction detail page
- **DoD:** any transaction's detail page reconstructs its full journey from the audit log alone.

### Phase 8 — Decision Receipt UI + Demo Polish `[PRD #7]`
- [ ] Decision Receipt component per §10.2 (approved + blocked variants)
- [ ] Buyer Simulator page per §10.3, with the live flow-stage tracker
- [ ] Standalone `/receipt/:id` shareable view
- [ ] Rehearse §15's script end to end
- **DoD:** the full happy-path + blocked-path demo runs live from the Buyer Simulator in under 3 minutes.

## 13. Environment & Run Commands

```bash
# backend/.env
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/ai_commerce_gateway
GEMINI_API_KEY=
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
JWT_SECRET=
MCP_TRANSPORT=streamable-http
MCP_PORT=8100
```

```bash
# backend
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m app.db.seed
uvicorn app.main:app --reload --port 8000

# frontend
cd frontend && npm install && npm run dev

# buyer client (demo)
cd buyer-client && pip install -r requirements.txt
python scripted_buyer.py --intent "Find me running shoes under ₹6,000"

# or, one shot:
docker-compose up
```

## 14. Testing Strategy

Don't over-invest in test coverage on a buildathon clock — but write these ones:
- **The single most important test in the whole system:** `checkout` never calls the Razorpay client when `policy_decision.approved == false`. Mock the Razorpay client, assert it's never invoked on a blocked decision. This is the test that protects the demo's punchline.
- Unit tests for `mandate_check()` and `policy_gate()` against §11's two demo carts — these are pure functions, cheap to test, and they're what "explainable by design" actually rests on.
- Skip frontend e2e tooling; the `/dev/components` showcase (Phase 0) plus the rehearsed demo script (§15) is your practical end-to-end check given the timeline.

## 15. Demo Script (3-minute walkthrough)

1. Open Buyer Simulator — mandate visible: **₹6,000 limit**.
2. Type/click *"Find me running shoes under ₹6,000"* → Run. Let the flow tracker light up stage by stage. Receipt renders: Velocity Pro ₹5,499 + Socks upsell ₹499 = **₹5,998**, approved, Razorpay verified.
3. Click preset *"Buy the ₹8,999 version instead"* → Run. Mandate Check fails immediately. Receipt: **BLOCKED — Razorpay was never called.** Pause on this — it's the strongest single proof point in the whole pitch.
4. Flip to the transaction's Audit Log to show both events logged transparently, end to end.
5. Close: this is the infrastructure layer that makes any merchant ready for the agentic-commerce world NPCI's UAP and the ACP/AP2/x402 protocols are converging on — today, not someday.

## 16. Assumptions & Open Questions

Places this document made a call the PRD didn't fully pin down. Flagged for you to override if any are wrong:

1. **Database:** Postgres over SQLite, to reuse your LowKey Secure pattern rather than optimize for zero-setup — worth it since docker-compose already makes setup one command.
2. **Auth:** single `merchant_admin` JWT role. No real multi-tenant RBAC — not worth building for a one-merchant demo.
3. **MCP transport:** Streamable HTTP, not stdio — so the Gateway is a real reachable service, not a subprocess.
4. **Mandate delivery:** `check_policy`/`checkout` accept a stored `mandate_id` (seeded) with an inline override available for testing, rather than requiring the full object on every call.
5. **Approval threshold behavior:** approval_threshold_amount is an autonomous-purchase threshold, not a maximum transaction or sales limit. Transactions above it are blocked in MVP with reason "merchant approval required for autonomous purchase" because no human-approval workflow exists. A future version can introduce a PENDING_MERCHANT_APPROVAL state.
6. **Decision Engine determinism:** hybrid design (deterministic pre-filter + lightweight fit scoring, Gemini mainly for intent-parsing and "why" text) rather than a full LLM-driven selection on every call — protects the live demo from LLM non-determinism while keeping genuine AI reasoning in the loop. This is *not* the same thing as the PRD's "fully autonomous LLM-driven AI buyer" stretch goal — that stretch goal means a free-form multi-turn agent, not just which component does the ranking.
7. **Razorpay flow:** real Checkout.js test-mode modal recommended over a server-simulated payment — more convincing for the "Razorpay verified" claim on stage.
8. **Typography:** can't extract the exact reference font pixel-for-pixel; Space Grotesk + Inter is a close, license-clean match to its geometric-grotesk character.
9. **Palette framing:** the black-navy + lime combination is kept exactly as referenced (your brief, your call) — flagged in §9 only for transparency, since it's a family of palette generic AI tools also reach for by default. The plan leans on layout, type, and content decisions to keep it reading as designed for this product rather than templated.
