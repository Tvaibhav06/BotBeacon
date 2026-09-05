import React, { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { Save, ShieldCheck, AlertTriangle, Info, CreditCard, CheckCircle2, XCircle, Clock } from "lucide-react";
import { api, MerchantRules, TransactionResult, PaymentVerifyResponse } from "../lib/api";
import { useAuth } from "../lib/AuthContext";
import { Card } from "../design-system/Card";
import { Button } from "../design-system/Button";
import { Badge } from "../design-system/Badge";
import { useRazorpayCheckout } from "../lib/useRazorpayCheckout";

// ─── helpers ─────────────────────────────────────────────────────────────────

function FieldLabel({
  label,
  hint,
}: {
  label: string;
  hint?: string;
}) {
  return (
    <div className="mb-1">
      <label className="block font-body text-sm font-medium text-ink">
        {label}
      </label>
      {hint && (
        <p className="font-body text-xs text-ink/50 mt-0.5 leading-snug">{hint}</p>
      )}
    </div>
  );
}

function NumberField({
  label,
  hint,
  value,
  onChange,
  min,
  max,
  step,
  suffix,
  disabled,
}: {
  label: string;
  hint?: string;
  value: number | string;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  suffix?: string;
  disabled?: boolean;
}) {
  return (
    <div>
      <FieldLabel label={label} hint={hint} />
      <div className="flex items-center gap-2">
        <input
          type="number"
          value={value}
          min={min}
          max={max}
          step={step ?? 1}
          disabled={disabled}
          onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
          className="
            w-full font-body text-sm text-ink border border-border rounded-lg
            px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-ink/20
            disabled:bg-surface disabled:text-ink/40
          "
        />
        {suffix && (
          <span className="font-body text-sm text-ink/50 shrink-0">{suffix}</span>
        )}
      </div>
    </div>
  );
}

// ─── info callout ─────────────────────────────────────────────────────────────

function InfoCallout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-3 bg-surface border border-border rounded-xl p-4">
      <Info size={16} className="text-ink/40 mt-0.5 shrink-0" />
      <p className="font-body text-xs text-ink/60 leading-relaxed">{children}</p>
    </div>
  );
}

// ─── main page ────────────────────────────────────────────────────────────────

const DEFAULT_RULES: MerchantRules = {
  max_ai_discount_pct: 10,
  upsell_enabled: true,
  preferred_categories: [],
  min_margin_pct: 15,
  approval_threshold_amount: 15000,
};

export function RulesPage() {
  const { token, merchantId } = useAuth();

  const [rules, setRules] = useState<MerchantRules>(DEFAULT_RULES);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Raw string for the preferred_categories textarea
  const [categoriesRaw, setCategoriesRaw] = useState("");

  // threshold toggle: null = no threshold
  const [thresholdEnabled, setThresholdEnabled] = useState(true);

  useEffect(() => {
    if (!merchantId || !token) return;
    setLoading(true);
    api
      .getRules(merchantId, token)
      .then((r) => {
        setRules(r);
        setCategoriesRaw((r.preferred_categories ?? []).join(", "));
        setThresholdEnabled(r.approval_threshold_amount != null);
      })
      .catch(() => {
        // No rules yet — use defaults
        setRules(DEFAULT_RULES);
        setCategoriesRaw("footwear, accessories");
        setThresholdEnabled(true);
      })
      .finally(() => setLoading(false));
  }, [merchantId, token]);

  function parseCategories(raw: string): string[] {
    return raw
      .split(/[,\n]/)
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean);
  }

  async function handleSave() {
    if (!merchantId || !token) return;
    setSaving(true);
    setError(null);
    setSaved(false);

    const payload: MerchantRules = {
      ...rules,
      preferred_categories: parseCategories(categoriesRaw),
      approval_threshold_amount: thresholdEnabled
        ? rules.approval_threshold_amount ?? 15000
        : null,
    };

    try {
      const updated = await api.saveRules(merchantId, payload, token);
      setRules(updated);
      setCategoriesRaw((updated.preferred_categories ?? []).join(", "));
      setThresholdEnabled(updated.approval_threshold_amount != null);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to save rules");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="p-8">
        <h1 className="font-heading text-2xl font-bold text-ink mb-2">Rules</h1>
        <p className="font-body text-sm text-ink/50">Loading rules…</p>
      </div>
    );
  }

  return (
    <div className="p-8 max-w-2xl">
      {/* Page header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-heading text-2xl font-bold text-ink">
            Merchant Rules
          </h1>
          <p className="font-body text-sm text-ink/50 mt-0.5">
            Deterministic guardrails enforced by the Policy Gate before every AI purchase.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ShieldCheck size={18} className="text-ink/40" />
          <span className="font-body text-xs text-ink/40">Policy Gate</span>
        </div>
      </div>

      {/* Save feedback */}
      {saved && (
        <div className="flex items-center gap-2 mb-4 bg-lime/20 border border-lime rounded-xl px-4 py-2">
          <ShieldCheck size={14} className="text-ink" />
          <span className="font-body text-sm text-ink font-medium">Rules saved.</span>
        </div>
      )}
      {error && (
        <div className="flex items-center gap-2 mb-4 bg-coral/10 border border-coral/30 rounded-xl px-4 py-2">
          <AlertTriangle size={14} className="text-coral" />
          <span className="font-body text-sm text-coral">{error}</span>
        </div>
      )}

      {/* ── Section: AI Discount ── */}
      <Card className="mb-4">
        <h2 className="font-heading text-base font-semibold text-ink mb-1">
          Discount Control
        </h2>
        <p className="font-body text-xs text-ink/50 mb-4">
          Maximum discount the AI may apply autonomously. 0% = no discounts allowed.
        </p>
        <NumberField
          label="Max AI discount"
          hint="Any cart item discounted beyond this % will be blocked by the Policy Gate."
          value={rules.max_ai_discount_pct}
          onChange={(v) => setRules((r) => ({ ...r, max_ai_discount_pct: v }))}
          min={0}
          max={100}
          step={0.5}
          suffix="%"
        />
      </Card>

      {/* ── Section: Margin Protection ── */}
      <Card className="mb-4">
        <h2 className="font-heading text-base font-semibold text-ink mb-1">
          Margin Protection
        </h2>
        <p className="font-body text-xs text-ink/50 mb-4">
          The Policy Gate checks every item's live margin before approving.
          Items sold below this floor are blocked.
        </p>
        <NumberField
          label="Minimum margin"
          hint="(price − cost) / price × 100 must be ≥ this value. Margin data is never exposed to the AI buyer."
          value={rules.min_margin_pct}
          onChange={(v) => setRules((r) => ({ ...r, min_margin_pct: v }))}
          min={0}
          max={100}
          step={0.5}
          suffix="%"
        />
      </Card>

      {/* ── Section: Autonomous Approval Threshold ── */}
      <Card className="mb-4">
        <h2 className="font-heading text-base font-semibold text-ink mb-1">
          Autonomous Approval Threshold
        </h2>
        <p className="font-body text-xs text-ink/50 mb-4">
          AI can execute purchases up to this amount without human review.
          Above it, the transaction is blocked until a merchant approves.
        </p>

        <InfoCallout>
          This is an <strong>autonomy boundary</strong>, not a payment ceiling. Your AI agent can still
          <em> quote</em> higher amounts — it just cannot <em>execute</em> them without merchant sign-off.
          Razorpay can always process any amount you approve manually.
        </InfoCallout>

        <div className="mt-4 flex items-center gap-3">
          <button
            type="button"
            onClick={() => setThresholdEnabled((v) => !v)}
            className={`
              relative inline-flex h-5 w-9 items-center rounded-full transition-colors
              ${thresholdEnabled ? "bg-ink" : "bg-ink/20"}
            `}
          >
            <span
              className={`
                inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform
                ${thresholdEnabled ? "translate-x-4" : "translate-x-1"}
              `}
            />
          </button>
          <span className="font-body text-sm text-ink">
            {thresholdEnabled ? "Enabled" : "Disabled (no threshold — AI can spend any amount)"}
          </span>
        </div>

        {thresholdEnabled && (
          <div className="mt-3">
            <NumberField
              label="Threshold amount"
              hint="Carts above this total require merchant approval for autonomous execution."
              value={rules.approval_threshold_amount ?? 15000}
              onChange={(v) =>
                setRules((r) => ({ ...r, approval_threshold_amount: v }))
              }
              min={0}
              step={500}
              suffix="₹"
            />
          </div>
        )}
      </Card>

      {/* ── Section: Upsell & Categories ── */}
      <Card className="mb-6">
        <h2 className="font-heading text-base font-semibold text-ink mb-1">
          Upsell & Categories
        </h2>
        <p className="font-body text-xs text-ink/50 mb-4">
          Upsell selection respects buyer mandate headroom — the AI will never recommend an
          upsell that would push the cart over the buyer's spending limit.
        </p>

        <div className="mb-4">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() =>
                setRules((r) => ({ ...r, upsell_enabled: !r.upsell_enabled }))
              }
              className={`
                relative inline-flex h-5 w-9 items-center rounded-full transition-colors
                ${rules.upsell_enabled ? "bg-ink" : "bg-ink/20"}
              `}
            >
              <span
                className={`
                  inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform
                  ${rules.upsell_enabled ? "translate-x-4" : "translate-x-1"}
                `}
              />
            </button>
            <span className="font-body text-sm text-ink">
              {rules.upsell_enabled ? "Upsell enabled" : "Upsell disabled"}
            </span>
          </div>
        </div>

        <div>
          <FieldLabel
            label="Preferred categories"
            hint="Comma-separated. Decision Engine scores products from these categories higher."
          />
          <textarea
            value={categoriesRaw}
            onChange={(e) => setCategoriesRaw(e.target.value)}
            rows={2}
            placeholder="footwear, accessories"
            className="
              w-full font-body text-sm text-ink border border-border rounded-lg
              px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-ink/20
              resize-none
            "
          />
          {/* Preview tags */}
          {parseCategories(categoriesRaw).length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {parseCategories(categoriesRaw).map((c) => (
                <Badge key={c} variant="surface">
                  {c}
                </Badge>
              ))}
            </div>
          )}
        </div>
      </Card>

      {/* ── Save ── */}
      <div className="flex items-center justify-between">
        <p className="font-body text-xs text-ink/40">
          Rules take effect on the next AI buyer request.
        </p>
        <Button
          variant="primary"
          size="md"
          onClick={handleSave}
          disabled={saving}
        >
          <Save size={14} />
          {saving ? "Saving…" : "Save Rules"}
        </Button>
      </div>
    </div>
  );
}

// Removed SimulatorPage and ReceiptPage since they are now implemented in their own files

// ── Transaction status helpers ────────────────────────────────────────────────

function StatusPill({ status }: { status: TransactionResult["status"] }) {
  const cfg: Record<string, { label: string; className: string; icon: React.ReactNode }> = {
    approved_paid:   { label: "Approved & Paid",  className: "bg-lime/20 text-ink border border-lime",        icon: <CheckCircle2 size={12} /> },
    pending_payment: { label: "Pending Payment",  className: "bg-amber-50 text-amber-800 border border-amber-200", icon: <Clock size={12} /> },
    blocked:         { label: "Blocked",           className: "bg-coral/10 text-coral border border-coral/30",  icon: <XCircle size={12} /> },
    failed:          { label: "Failed",            className: "bg-coral/10 text-coral border border-coral/30",  icon: <XCircle size={12} /> },
  };
  const { label, className, icon } = cfg[status] ?? { label: status, className: "bg-surface text-ink border border-border", icon: null };
  return (
    <span className={`inline-flex items-center gap-1 font-body text-xs font-medium px-2.5 py-1 rounded-full ${className}`}>
      {icon}{label}
    </span>
  );
}

// ── TransactionsPage ──────────────────────────────────────────────────────────

export function TransactionsPage() {
  const { token, merchantId } = useAuth();
  const { openCheckout } = useRazorpayCheckout();

  const [txns, setTxns] = useState<TransactionResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // map of txn_id → PaymentVerifyResponse for just-verified rows
  const [verifiedMap, setVerifiedMap] = useState<Record<string, PaymentVerifyResponse>>({});
  const [payingId, setPayingId] = useState<string | null>(null);

  const loadTxns = useCallback(() => {
    if (!merchantId || !token) return;
    setLoading(true);
    api
      .listTransactions(merchantId, token)
      .then(setTxns)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load transactions"))
      .finally(() => setLoading(false));
  }, [merchantId, token]);

  useEffect(() => { loadTxns(); }, [loadTxns]);

  async function handlePay(txn: TransactionResult) {
    if (!txn.razorpay_order_id || !token) return;
    setPayingId(txn.id);
    try {
      await openCheckout({
        razorpay_order_id: txn.razorpay_order_id,
        amount: txn.amount,
        transaction_id: txn.id,
        token,
        onVerified: (result) => {
          setVerifiedMap((m) => ({ ...m, [txn.id]: result }));
          // Refresh the list so status reflects approved_paid
          loadTxns();
          setPayingId(null);
        },
        onDismissed: () => setPayingId(null),
      });
    } catch {
      setPayingId(null);
    }
  }

  if (loading) {
    return (
      <div className="p-8">
        <h1 className="font-heading text-2xl font-bold text-ink mb-2">Transactions</h1>
        <p className="font-body text-sm text-ink/50">Loading…</p>
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-heading text-2xl font-bold text-ink">Transactions</h1>
          <p className="font-body text-sm text-ink/50 mt-0.5">
            AI-buyer purchase history. Pending transactions can be completed via Razorpay.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={loadTxns}>
          Refresh
        </Button>
      </div>

      {error && (
        <div className="flex items-center gap-2 mb-4 bg-coral/10 border border-coral/30 rounded-xl px-4 py-2">
          <AlertTriangle size={14} className="text-coral" />
          <span className="font-body text-sm text-coral">{error}</span>
        </div>
      )}

      {txns.length === 0 ? (
        <Card>
          <p className="font-body text-sm text-ink/50 text-center py-8">
            No transactions yet. Run the buyer simulator to create one.
          </p>
        </Card>
      ) : (
        <div className="border border-border rounded-2xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface border-b border-border">
                <th className="text-left font-body font-semibold text-ink/60 px-4 py-3">Transaction ID</th>
                <th className="text-left font-body font-semibold text-ink/60 px-4 py-3">Amount</th>
                <th className="text-left font-body font-semibold text-ink/60 px-4 py-3">Razorpay Order</th>
                <th className="text-left font-body font-semibold text-ink/60 px-4 py-3">Status</th>
                <th className="text-left font-body font-semibold text-ink/60 px-4 py-3">Action</th>
              </tr>
            </thead>
            <tbody>
              {txns.map((txn, i) => {
                const verified = verifiedMap[txn.id];
                const isLast = i === txns.length - 1;
                return (
                  <tr
                    key={txn.id}
                    className={`bg-white hover:bg-surface/60 transition-colors ${!isLast ? "border-b border-border" : ""}`}
                  >
                    <td className="px-4 py-3 font-mono text-xs text-ink/70">
                      <Link to={`/transactions/${txn.id}/audit`} className="hover:text-blue hover:underline">
                        {txn.id}
                      </Link>
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-ink font-medium">₹{txn.amount.toLocaleString("en-IN")}</td>
                    <td className="px-4 py-3 font-mono text-xs text-ink/50">
                      {txn.razorpay_order_id ?? <span className="text-coral/60 italic">none — blocked</span>}
                    </td>
                    <td className="px-4 py-3">
                      <StatusPill status={verified ? verified.status as TransactionResult["status"] : txn.status} />
                    </td>
                    <td className="px-4 py-3">
                      {txn.status === "pending_payment" && txn.razorpay_order_id && !verified ? (
                        <Button
                          id={`pay-btn-${txn.id}`}
                          variant="lime"
                          size="sm"
                          loading={payingId === txn.id}
                          disabled={!!payingId}
                          onClick={() => handlePay(txn)}
                        >
                          <CreditCard size={13} />
                          Pay Now
                        </Button>
                      ) : verified ? (
                        <span className="font-body text-xs text-ink/50">
                          {verified.verified ? "✓ Verified" : "✗ Mismatch"}
                          {verified.discrepancies.length > 0 && (
                            <span className="text-coral ml-1">({verified.discrepancies[0]})</span>
                          )}
                        </span>
                      ) : (
                        <span className="font-body text-xs text-ink/30">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function AuditLogPage() {
  return (
    <div className="p-8">
      <h1 className="font-heading text-2xl font-bold text-ink mb-2">Audit Log</h1>
      <p className="font-body text-sm text-ink/50 mb-6">Append-only audit trail — implemented in Phase 7</p>
      <Card>
        <p className="font-body text-sm text-ink/50 text-center py-8">
          Audit Log will be available after Phase 7.
        </p>
      </Card>
    </div>
  );
}
