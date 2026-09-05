/**
 * Thin API client for the AI Commerce Gateway backend.
 * All requests go to /api (proxied to :8000 by Vite in development).
 */

const BASE = "/api";

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

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body != null ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
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
    fetch(`${BASE}/merchants/${merchantId}/catalog/${productId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    }),

  uploadCatalogCsv: (merchantId: string, file: File, token: string) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`${BASE}/merchants/${merchantId}/catalog/upload`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    }).then((r) => r.json());
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

  getReceipt: (transactionId: string, token: string) =>
    request<DecisionReceipt>("GET", `/transactions/${transactionId}/receipt`, undefined, token),

  getAuditTrail: (transactionId: string, token: string) =>
    request<AuditLogEntry[]>("GET", `/transactions/${transactionId}/audit-trail`, undefined, token),

  getAuditLog: (merchantId: string, token: string, stage?: string) =>
    request<AuditLogEntry[]>(
      "GET",
      `/merchants/${merchantId}/audit-log${stage ? `?stage=${stage}` : ""}`,
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
