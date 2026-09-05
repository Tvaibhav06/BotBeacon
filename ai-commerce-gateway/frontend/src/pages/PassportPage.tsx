import React, { useEffect, useState, useCallback } from "react";
import {
  AlertTriangle, AlertCircle, CheckCircle, RefreshCw, Plus, ShieldCheck
} from "lucide-react";
import { Button } from "../design-system/Button";
import { Card } from "../design-system/Card";
import { Badge } from "../design-system/Badge";
import { api, PassportResponse, ValidationIssue, Product } from "../lib/api";
import { useAuth } from "../lib/AuthContext";

const INR = (n: number) => `₹${n.toLocaleString("en-IN")}`;

function ValidationBadge({ issue }: { issue: ValidationIssue }) {
  return (
    <div className={[
      "flex items-start gap-2 px-3 py-2 rounded-lg text-xs font-body",
      issue.severity === "error"
        ? "bg-coral/10 text-coral border border-coral/20"
        : "bg-lime/10 text-ink/70 border border-lime/20"
    ].join(" ")}>
      {issue.severity === "error"
        ? <AlertCircle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
        : <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
      }
      <span><strong>{issue.field}:</strong> {issue.message}</span>
    </div>
  );
}

function ProductRow({ product, issues }: { product: Product; issues: ValidationIssue[] }) {
  const margin = product.price > 0
    ? ((product.price - product.cost) / product.price * 100).toFixed(1)
    : "—";

  const hasError = issues.some(i => i.product_id === product.id && i.severity === "error");
  const hasWarning = issues.some(i => i.product_id === product.id && i.severity === "warning");
  const productIssues = issues.filter(i => i.product_id === product.id);

  return (
    <tr className="border-b border-border hover:bg-surface/60 transition-colors">
      <td className="px-4 py-3">
        <div className="font-body text-sm font-medium text-ink">{product.name}</div>
        <div className="font-body text-xs text-ink/40 mt-0.5">{product.id}</div>
      </td>
      <td className="px-4 py-3">
        <Badge variant="surface">{product.category}</Badge>
      </td>
      <td className="px-4 py-3 font-body text-sm text-ink text-right">{INR(product.price)}</td>
      <td className="px-4 py-3 font-body text-sm text-ink/50 text-right">{INR(product.cost)}</td>
      <td className="px-4 py-3 font-body text-sm text-ink/70 text-right">{margin}%</td>
      <td className="px-4 py-3 font-body text-sm text-ink text-right">{product.stock}</td>
      <td className="px-4 py-3">
        <Badge variant={product.status === "active" ? "lime" : "surface"}>
          {product.status}
        </Badge>
      </td>
      <td className="px-4 py-3">
        {hasError && <Badge variant="coral">Error</Badge>}
        {!hasError && hasWarning && <Badge variant="surface">Warning</Badge>}
        {!hasError && !hasWarning && <Badge variant="lime">✓</Badge>}
        {productIssues.length > 0 && (
          <div className="mt-1 space-y-1">
            {productIssues.map((issue, i) => (
              <ValidationBadge key={i} issue={issue} />
            ))}
          </div>
        )}
      </td>
    </tr>
  );
}

export function PassportPage() {
  const { token, merchantId } = useAuth();
  const [passport, setPassport] = useState<PassportResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [activating, setActivating] = useState(false);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  const load = useCallback(async () => {
    if (!token || !merchantId) return;
    setLoading(true);
    try {
      const data = await api.getPassport(merchantId, token);
      setPassport(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load passport");
    } finally {
      setLoading(false);
    }
  }, [token, merchantId]);

  useEffect(() => { load(); }, [load]);

  const handleActivate = async () => {
    if (!token || !merchantId) return;
    setActivating(true);
    setError("");
    setSuccessMsg("");
    try {
      const data = await api.activatePassport(merchantId, token);
      setPassport(data);
      setSuccessMsg("Passport activated! Your catalog is now AI-buyer-ready.");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Activation failed");
    } finally {
      setActivating(false);
    }
  };

  const errorCount = passport?.validation_issues.filter(i => i.severity === "error").length ?? 0;
  const warnCount = passport?.validation_issues.filter(i => i.severity === "warning").length ?? 0;

  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="font-heading text-2xl font-bold text-ink">Passport &amp; Catalog</h1>
          <p className="font-body text-sm text-ink/50 mt-1">
            {passport?.products.length ?? 0} products · Passport{" "}
            <span className={passport?.passport_status === "active" ? "text-ink font-medium" : "text-ink/40"}>
              {passport?.passport_status?.toUpperCase() ?? "—"}
            </span>
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load}>
            <RefreshCw className="w-4 h-4" strokeWidth={1.75} />
            Refresh
          </Button>
          {passport?.passport_status !== "active" && (
            <Button
              variant="lime"
              size="sm"
              loading={activating}
              disabled={!passport?.can_activate}
              onClick={handleActivate}
            >
              <ShieldCheck className="w-4 h-4" strokeWidth={1.75} />
              Activate Passport
            </Button>
          )}
        </div>
      </div>

      {/* Status banner */}
      {passport?.passport_status === "active" && (
        <div className="flex items-center gap-2 bg-lime/20 border border-lime/30 rounded-card px-4 py-3 mb-6">
          <CheckCircle className="w-4 h-4 text-ink" strokeWidth={2} />
          <span className="font-body text-sm text-ink font-medium">
            Commerce Passport is ACTIVE — your catalog is AI-buyer-ready
          </span>
        </div>
      )}

      {/* Validation summary */}
      {(errorCount > 0 || warnCount > 0) && (
        <div className="grid grid-cols-2 gap-3 mb-6">
          {errorCount > 0 && (
            <div className="flex items-center gap-3 bg-coral/10 border border-coral/20 rounded-card px-4 py-3">
              <AlertCircle className="w-5 h-5 text-coral flex-shrink-0" />
              <div>
                <p className="font-body text-sm font-medium text-coral">{errorCount} error{errorCount !== 1 ? "s" : ""}</p>
                <p className="font-body text-xs text-ink/50">Blocks activation</p>
              </div>
            </div>
          )}
          {warnCount > 0 && (
            <div className="flex items-center gap-3 bg-lime/10 border border-lime/30 rounded-card px-4 py-3">
              <AlertTriangle className="w-5 h-5 text-ink/60 flex-shrink-0" />
              <div>
                <p className="font-body text-sm font-medium text-ink/70">{warnCount} warning{warnCount !== 1 ? "s" : ""}</p>
                <p className="font-body text-xs text-ink/40">Does not block activation</p>
              </div>
            </div>
          )}
        </div>
      )}

      {error && <p className="text-coral font-body text-sm mb-4">{error}</p>}
      {successMsg && <p className="text-ink font-body text-sm mb-4 font-medium">{successMsg}</p>}

      {loading ? (
        <div className="text-center py-16 text-ink/40 font-body text-sm">Loading catalog…</div>
      ) : (
        <Card className="p-0 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="bg-ink text-white">
                {["Product", "Category", "Price", "Cost", "Margin", "Stock", "Status", "Validation"].map(h => (
                  <th
                    key={h}
                    className="px-4 py-3 text-left font-body font-medium text-xs tracking-wide text-white/70 first:text-left"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {passport?.products.map(p => (
                <ProductRow
                  key={p.id}
                  product={p}
                  issues={passport.validation_issues.filter(i => i.product_id === p.id)}
                />
              ))}
              {(!passport?.products || passport.products.length === 0) && (
                <tr>
                  <td colSpan={8} className="text-center py-12 text-ink/40 font-body text-sm">
                    No products yet. Upload a CSV or add products manually.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
