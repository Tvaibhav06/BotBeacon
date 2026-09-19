/**
 * Thin API client for the AI Commerce Gateway backend.
 * Base URL is environment-driven via VITE_API_URL or defaults to /api (Vite dev proxy).
 */

const VITE_API_URL = ((import.meta as any).env?.VITE_API_URL as string | undefined)?.replace(/\/$/, "");
export const API_BASE = VITE_API_URL ? `${VITE_API_URL}/api` : "/api";

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, message: string, detail?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail ?? message;
  }

  get isNetworkError(): boolean {
    return this.status === 0;
  }
  get isUnauthorized(): boolean {
    return this.status === 401;
  }
  get isForbidden(): boolean {
    return this.status === 403;
  }
  get isNotFound(): boolean {
    return this.status === 404;
  }
  get isServerError(): boolean {
    return this.status >= 500;
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  token?: string
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body != null ? JSON.stringify(body) : undefined,
    });
  } catch (netErr: any) {
    throw new ApiError(0, "Network failure: Unable to connect to server. Please check your network connection.", netErr?.message);
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText || `HTTP ${res.status}` }));
    const detailMsg = typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail ?? `HTTP ${res.status}`);
    throw new ApiError(res.status, detailMsg, detailMsg);
  }
  return res.json();
}

export const api = {
  // Auth
  login: (email: string, password: string) =>
    request<{ access_token: string; token_type: string }>("POST", "/auth/login", { email, password }),

  // Merchant
  onboard: (name: string, email: string, password: string) =>
    request("POST", "/merchants/onboard", { name, email, password }),

  getMerchant: (id: string, token: string) =>
    request<Merchant>("GET", `/merchants/${id}`, undefined, token),

  // Catalog
  addProduct: (merchantId: string, product: ProductCreate, token: string) =>
    request<Product>("POST", `/merchants/${merchantId}/catalog`, product, token),

  updateProduct: (merchantId: string, productId: string, update: Partial<ProductCreate>, token: string) =>
    request<Product>("PUT", `/merchants/${merchantId}/catalog/${productId}`, update, token),

  deleteProduct: (merchantId: string, productId: string, token: string) =>
    request<void>("DELETE", `/merchants/${merchantId}/catalog/${productId}`, undefined, token),

  uploadCatalogCsv: async (merchantId: string, file: File, token: string) => {
    const form = new FormData();
    form.append("file", file);
    let r: Response;
    try {
      r = await fetch(`${API_BASE}/merchants/${merchantId}/catalog/upload`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
    } catch (netErr: any) {
      throw new ApiError(0, "Network failure: Unable to upload CSV", netErr?.message);
    }
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText || `HTTP ${r.status}` }));
      throw new ApiError(r.status, err.detail ?? `HTTP ${r.status}`);
    }
    return r.json();
  },

  // Passport
  getPassport: (merchantId: string, token: string) =>
    request<PassportResponse>("GET", `/merchants/${merchantId}/passport`, undefined, token),

  activatePassport: (merchantId: string, token: string) =>
    request<PassportResponse>("POST", `/merchants/${merchantId}/passport/activate`, undefined, token),

  // Rules
  getRules: (merchantId: string, token: string) =>
    request<MerchantRules>("GET", `/merchants/${merchantId}/rules`, undefined, token),

  saveRules: (merchantId: string, rules: MerchantRules, token: string) =>
    request<MerchantRules>("POST", `/merchants/${merchantId}/rules`, rules, token),

  // Transactions
  listTransactions: (merchantId: string, token: string) =>
    request<TransactionResult[]>("GET", `/merchants/${merchantId}/transactions`, undefined, token),

  getReceipt: (transactionId: string) =>
    request<DecisionReceipt>("GET", `/transactions/${transactionId}/receipt`),

  getAuditTrail: (transactionId: string, token: string) =>
    request<AuditLogEntry[]>("GET", `/transactions/${transactionId}/audit-trail`, undefined, token),

  getAuditLog: (merchantId: string, token: string, stage?: string) =>
    request<AuditLogEntry[]>(
      "GET",
      `/merchants/${merchantId}/audit-log${stage ? `?stage=${stage}` : ""}`,
      undefined,
      token
    ),

  // Growth AI (Phase 4 & 5)
  getGrowthInsights: (merchantId: string, token: string) =>
    request<SalesInsights>("GET", `/merchants/${merchantId}/growth/insights`, undefined, token),

  getGrowthOpportunities: (merchantId: string, token: string, status?: string) =>
    request<GrowthOpportunity[]>(
      "GET",
      `/merchants/${merchantId}/growth/opportunities${status ? `?status=${status}` : ""}`,
      undefined,
      token
    ),

  scanGrowthOpportunities: (merchantId: string, token: string, discountPct?: number) =>
    request<GrowthScanResponse>(
      "POST",
      `/merchants/${merchantId}/growth/opportunities/scan${discountPct ? `?discount_pct=${discountPct}` : ""}`,
      undefined,
      token
    ),

  getGrowthOpportunity: (merchantId: string, oppId: string, token: string) =>
    request<GrowthOpportunity>("GET", `/merchants/${merchantId}/growth/opportunities/${oppId}`, undefined, token),

  approveGrowthOpportunity: (merchantId: string, oppId: string, token: string) =>
    request<{ message: string; opportunity_id: string; execution_id: string; status: string }>(
      "POST",
      `/merchants/${merchantId}/growth/opportunities/${oppId}/approve`,
      undefined,
      token
    ),

  rejectGrowthOpportunity: (merchantId: string, oppId: string, token: string) =>
    request<{ message: string; opportunity_id: string; status: string }>(
      "POST",
      `/merchants/${merchantId}/growth/opportunities/${oppId}/reject`,
      undefined,
      token
    ),

  // Payments (Phase 6)
  getPaymentConfig: (token: string) =>
    request<PaymentConfig>("GET", "/payments/config", undefined, token),

  verifyPayment: (body: PaymentVerifyRequest, token: string) =>
    request<PaymentVerifyResponse>("POST", "/payments/verify", body, token),
};

// ----- Types (mirrors backend Pydantic schemas §5) -----

export interface Product {
  id: string;
  name: string;
  category: string;
  tags: string[];
  price: number;
  cost: number;
  stock: number;
  complement_categories: string[];
  description: string;
  image_url?: string;
  status: "active" | "inactive";
}

export interface ProductCreate {
  id?: string;
  name: string;
  category: string;
  tags?: string[];
  price: number;
  cost: number;
  stock: number;
  complement_categories?: string[];
  description?: string;
  status?: "active" | "inactive";
}

export interface MerchantRules {
  max_ai_discount_pct: number;
  upsell_enabled: boolean;
  preferred_categories: string[];
  min_margin_pct: number;
  approval_threshold_amount?: number | null;
  growth_approval_threshold_amount?: number | null;
  growth_actions_enabled?: boolean;
}

export interface Merchant {
  id: string;
  name: string;
  email: string;
  passport_status: "draft" | "active";
  rules?: MerchantRules;
}

export interface ValidationIssue {
  product_id: string;
  field: string;
  message: string;
  severity: "error" | "warning";
}

export interface PassportResponse {
  merchant_id: string;
  passport_status: "draft" | "active";
  products: Product[];
  validation_issues: ValidationIssue[];
  can_activate: boolean;
}

export interface TransactionResult {
  id: string;
  cart_id: string;
  razorpay_order_id?: string;
  status: "approved_paid" | "blocked" | "failed" | "pending_payment";
  amount: number;
}

// Razorpay public config (KEY_SECRET is never included)
export interface PaymentConfig {
  key_id: string;
  currency: string;
}

// Payload sent to POST /api/payments/verify after Checkout.js fires payment.success
export interface PaymentVerifyRequest {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}

export interface PaymentVerifyResponse {
  transaction_id: string;
  verified: boolean;
  status: "approved_paid" | "blocked" | "failed" | "pending_payment";
  discrepancies: string[];
}

export interface DecisionReceipt {
  transaction_id: string;
  customer_request: string;
  ai_considered_count?: number;
  selected?: { product_id: string; quantity: number; unit_price: number; role: string };
  why: string[];
  upsell?: { product_id: string; quantity: number; unit_price: number; role: string };
  final_total: number;
  authorization_status: string;
  payment_status: string;
  _transaction_status?: string;
  _razorpay_order_id?: string;
}

export interface AuditLogEntry {
  id: string;
  timestamp: string;
  merchant_id: string;
  transaction_id?: string;
  cart_id?: string;
  stage: string;
  actor: string;
  payload: Record<string, unknown>;
  result: Record<string, unknown>;
}

// ----- Growth AI Types (§6.2, §6.3, §6.5) -----

export interface TopProductInsight {
  product_id: string;
  product_name: string;
  units_sold: number;
  revenue: number;
}

export interface DecliningProductInsight {
  product_id: string;
  product_name: string;
  recent_weekly_units: number;
  prior_weekly_units: number;
  units_drop_pct: number;
}

export interface SalesInsights {
  trend_pct?: number | null;
  total_units_recent?: number | null;
  total_revenue_recent?: number | null;
  total_units_prior?: number | null;
  total_revenue_prior?: number | null;
  top_products?: TopProductInsight[];
  declining_products?: DecliningProductInsight[];
}

export interface GrowthRecommendedAction {
  type: string;
  product_ids?: string[];
  discount_pct?: number;
  campaign_duration_weeks?: number;
  audience?: string;
  [key: string]: unknown;
}

export interface GrowthOpportunity {
  id: string;
  merchant_id: string;
  opportunity_type: string;
  title: string;
  evidence?: Record<string, unknown>;
  recommended_action?: GrowthRecommendedAction;
  estimated_discount_exposure?: number | null;
  policy_outcome: "allowed" | "requires_approval" | "blocked" | string;
  policy_reasons?: string[];
  status: "new" | "pending_approval" | "executing" | "completed" | "rejected_by_merchant" | "blocked" | "failed" | string;
  created_at?: string;
  updated_at?: string;
}

export interface GrowthScanResponse {
  scanned_at: string;
  created_count: number;
  opportunities: GrowthOpportunity[];
}

export interface GrowthExecution {
  id: string;
  opportunity_id: string;
  n8n_run_id?: string;
  status: string;
  request_payload?: Record<string, unknown>;
  result_payload?: Record<string, unknown>;
  error?: string;
  started_at: string;
  completed_at?: string;
}

// ----- Copilot SSE Streaming Client (§6.1) -----

export async function streamCopilotChat(
  merchantId: string,
  message: string,
  token: string,
  callbacks: {
    onChunk: (text: string) => void;
    onTool?: (tool: { name: string; status: string }) => void;
    onOpportunity?: (opp: any) => void;
    onDone?: (oppId?: string) => void;
  },
  history?: Array<{ role: string; content: string }>
) {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/merchants/${merchantId}/copilot/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ message, history: history || [] }),
    });
  } catch (netErr: any) {
    throw new ApiError(0, "Network failure: Unable to reach Copilot service", netErr?.message);
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, err.detail ?? `HTTP ${res.status}`);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new ApiError(res.status, "No response body stream");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith("data:")) {
        try {
          const data = JSON.parse(trimmed.slice(5).trim());
          if (data.type === "chunk" && data.text) {
            callbacks.onChunk(data.text);
          } else if (data.type === "tool") {
            callbacks.onTool?.(data);
          } else if (data.type === "opportunity") {
            callbacks.onOpportunity?.(data.opportunity);
          } else if (data.type === "done") {
            callbacks.onDone?.(data.opportunity_id);
          }
        } catch {
          // ignore partial JSON
        }
      }
    }
  }
}
