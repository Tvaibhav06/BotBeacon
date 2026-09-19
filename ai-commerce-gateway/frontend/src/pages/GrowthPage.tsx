import React, { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import {
  TrendingUp,
  TrendingDown,
  Sparkles,
  RefreshCw,
  Search,
  CheckCircle2,
  Clock,
  ShieldAlert,
  ArrowRight,
  Package,
  Layers,
  AlertCircle,
} from "lucide-react";
import { useAuth } from "../lib/AuthContext";
import {
  api,
  ApiError,
  SalesInsights,
  GrowthOpportunity,
  MerchantRules,
} from "../lib/api";
import { formatNumber, formatCurrency, formatDate } from "../lib/formatters";
import { Card } from "../design-system/Card";
import { Button } from "../design-system/Button";
import { Badge } from "../design-system/Badge";
import { OpportunityCard } from "../components/OpportunityCard";

export function GrowthPage() {
  const { merchantId, token } = useAuth();

  const [insights, setInsights] = useState<SalesInsights | null>(null);
  const [insightsError, setInsightsError] = useState<string | null>(null);
  const [opportunities, setOpportunities] = useState<GrowthOpportunity[]>([]);
  const [oppsError, setOppsError] = useState<string | null>(null);
  const [rules, setRules] = useState<MerchantRules | null>(null);
  const [rulesError, setRulesError] = useState<string | null>(null);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [selectedFilter, setSelectedFilter] = useState<string>("all");
  const [message, setMessage] = useState<{ text: string; type: "success" | "error" } | null>(null);

  const loadData = useCallback(async () => {
    if (!merchantId || !token) return;
    setLoading(true);
    setGlobalError(null);
    try {
      const [insRes, oppsRes, rulesRes] = await Promise.allSettled([
        api.getGrowthInsights(merchantId, token),
        api.getGrowthOpportunities(merchantId, token),
        api.getRules(merchantId, token),
      ]);

      // Check for auth failures (401)
      const allResults = [insRes, oppsRes, rulesRes];
      const hasAuthError = allResults.some(
        (r) => r.status === "rejected" && r.reason instanceof ApiError && r.reason.isUnauthorized
      );
      if (hasAuthError) {
        setGlobalError("Authentication session expired. Please sign in again.");
        return;
      }

      const hasForbiddenError = allResults.some(
        (r) => r.status === "rejected" && r.reason instanceof ApiError && r.reason.isForbidden
      );
      if (hasForbiddenError) {
        setGlobalError("Access denied: You do not have permission to view this merchant's growth data.");
        return;
      }

      // If all three calls rejected, show global failure
      if (allResults.every((r) => r.status === "rejected")) {
        const firstErr = (insRes as PromiseRejectedResult).reason;
        const msg = firstErr instanceof ApiError
          ? (firstErr.isNetworkError ? "Network failure: Unable to reach gateway server. Please check your connection." : `Server error (HTTP ${firstErr.status}): ${firstErr.detail}`)
          : firstErr instanceof Error ? firstErr.message : "Failed to load growth data";
        setGlobalError(msg);
        return;
      }

      // Section: Insights
      if (insRes.status === "fulfilled") {
        setInsights(insRes.value);
        setInsightsError(null);
      } else {
        const err = insRes.reason;
        setInsights(null);
        setInsightsError(err instanceof ApiError ? err.detail : "Failed to load sales insights");
      }

      // Section: Opportunities
      if (oppsRes.status === "fulfilled") {
        setOpportunities(Array.isArray(oppsRes.value) ? oppsRes.value : []);
        setOppsError(null);
      } else {
        const err = oppsRes.reason;
        setOpportunities([]);
        setOppsError(err instanceof ApiError ? err.detail : "Failed to load growth opportunities");
      }

      // Section: Rules
      if (rulesRes.status === "fulfilled") {
        setRules(rulesRes.value);
        setRulesError(null);
      } else {
        setRules(null);
        setRulesError("Merchant rules unavailable");
      }
    } catch (err: any) {
      setGlobalError(err.message || "Failed to load growth data");
    } finally {
      setLoading(false);
    }
  }, [merchantId, token]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleScan = async () => {
    if (!merchantId || !token) return;
    setScanning(true);
    setMessage(null);
    try {
      const res = await api.scanGrowthOpportunities(merchantId, token, 10.0);
      setMessage({
        text: `Opportunity scan complete. Discovered and analyzed ${res.opportunities.length} growth proposals.`,
        type: "success",
      });
      loadData();
    } catch (err: any) {
      setMessage({ text: err.message || "Scan failed", type: "error" });
    } finally {
      setScanning(false);
    }
  };

  const handleApprove = async (oppId: string) => {
    if (!merchantId || !token) return;
    const res = await api.approveGrowthOpportunity(merchantId, oppId, token);
    setMessage({
      text: `Approved #${oppId}. Fresh policy gate verified current rules. Execution ${res.execution_id} triggered to n8n.`,
      type: "success",
    });
    await loadData();
  };

  const handleReject = async (oppId: string) => {
    if (!merchantId || !token) return;
    await api.rejectGrowthOpportunity(merchantId, oppId, token);
    setMessage({
      text: `Opportunity #${oppId} rejected. n8n was not called.`,
      type: "success",
    });
    await loadData();
  };

  // Filter opportunities
  const filteredOpps = opportunities.filter((o) => {
    if (selectedFilter === "pending") return o.status === "pending_approval";
    if (selectedFilter === "completed") return o.status === "completed" || o.status === "executing";
    if (selectedFilter === "blocked") return o.status === "blocked" || o.policy_outcome === "blocked";
    return true;
  });

  const pendingCount = opportunities.filter((o) => o.status === "pending_approval").length;
  const completedCount = opportunities.filter((o) => o.status === "completed").length;

  if (globalError) {
    return (
      <div className="p-8 max-w-6xl">
        <div className="flex items-center gap-2 mb-6">
          <h1 className="font-heading text-2xl font-bold text-ink">Growth AI</h1>
        </div>
        <Card className="p-8 text-center bg-white border border-border">
          <div className="flex flex-col items-center justify-center max-w-md mx-auto">
            <div className="w-10 h-10 rounded-full bg-coral/10 flex items-center justify-center text-coral mb-3">
              <AlertCircle size={20} />
            </div>
            <h3 className="font-heading font-semibold text-ink text-base mb-1">
              Failed to load Growth dashboard
            </h3>
            <p className="font-body text-xs text-ink/60 mb-4 leading-relaxed">{globalError}</p>
            <Button variant="outline" size="sm" onClick={loadData}>
              Retry
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="p-8 max-w-6xl">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h1 className="font-heading text-2xl font-bold text-ink">Growth AI</h1>
            <Badge variant="surface">
              <Sparkles className="w-3.5 h-3.5 text-ink mr-1" />
              Autonomous Merchant Copilot
            </Badge>
          </div>
          <p className="font-body text-sm text-ink/60">
            Autonomous growth discovery governed by deterministic policy guardrails and merchant approval.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={loadData}
            disabled={loading}
            className="flex items-center gap-1.5"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={handleScan}
            disabled={scanning || loading}
            className="flex items-center gap-1.5 border-ink/30 text-ink"
          >
            <Search className={`w-3.5 h-3.5 ${scanning ? "animate-spin" : ""}`} />
            {scanning ? "Scanning Catalog..." : "Scan Opportunities"}
          </Button>

          <Link to="/copilot">
            <Button
              variant="primary"
              size="sm"
              className="bg-lime text-ink hover:bg-lime/90 font-medium flex items-center gap-1.5 shadow-sm"
            >
              <Sparkles className="w-3.5 h-3.5" />
              Ask Copilot
            </Button>
          </Link>
        </div>
      </div>

      {/* Message / Notification Banner */}
      {message && (
        <div
          className={`mb-6 p-3.5 rounded-xl border text-sm flex items-center justify-between ${
            message.type === "success"
              ? "bg-lime/15 border-lime text-ink"
              : "bg-coral/10 border-coral/30 text-coral"
          }`}
        >
          <span>{message.text}</span>
          <button
            onClick={() => setMessage(null)}
            className="text-xs opacity-60 hover:opacity-100 font-bold ml-4"
          >
            ✕
          </button>
        </div>
      )}

      {/* Section-specific error for sales insights */}
      {insightsError && (
        <div className="mb-6 p-3.5 rounded-xl bg-coral/10 border border-coral/30 flex items-center justify-between text-xs text-coral">
          <div className="flex items-center gap-2">
            <AlertCircle size={16} className="shrink-0" />
            <span>{insightsError}</span>
          </div>
          <Button variant="outline" size="sm" onClick={loadData} className="text-xs h-7">
            Retry Insights
          </Button>
        </div>
      )}

      {/* KPI Overview Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {/* Trend */}
        <Card className="p-4 bg-white border border-border">
          <p className="font-body text-xs font-medium text-ink/50 uppercase tracking-wider mb-1">
            14-Day Sales Trend
          </p>
          <div className="flex items-baseline gap-2">
            <span className="font-heading font-bold text-2xl text-ink">
              {formatCurrency(insights?.total_revenue_recent)}
            </span>
            {insights && typeof insights.trend_pct === "number" && Number.isFinite(insights.trend_pct) && (
              <span
                className={`inline-flex items-center text-xs font-semibold px-1.5 py-0.5 rounded ${
                  insights.trend_pct < 0
                    ? "text-coral bg-coral/10"
                    : "text-emerald-700 bg-emerald-50"
                }`}
              >
                {insights.trend_pct < 0 ? (
                  <TrendingDown className="w-3 h-3 mr-0.5" />
                ) : (
                  <TrendingUp className="w-3 h-3 mr-0.5" />
                )}
                {insights.trend_pct.toFixed(1)}%
              </span>
            )}
          </div>
          <p className="font-body text-xs text-ink/40 mt-1">
            Prior window: {formatCurrency(insights?.total_revenue_prior)}
          </p>
        </Card>

        {/* Units Sold */}
        <Card className="p-4 bg-white border border-border">
          <p className="font-body text-xs font-medium text-ink/50 uppercase tracking-wider mb-1">
            Units Sold (14-Day)
          </p>
          <div className="flex items-baseline gap-2">
            <span className="font-heading font-bold text-2xl text-ink">
              {formatNumber(insights?.total_units_recent)}
            </span>
            <span className="text-xs text-ink/50">units</span>
          </div>
          <p className="font-body text-xs text-ink/40 mt-1">
            Prior window: {formatNumber(insights?.total_units_prior)} units
          </p>
        </Card>

        {/* Active Proposals */}
        <Card className="p-4 bg-white border border-border">
          <p className="font-body text-xs font-medium text-ink/50 uppercase tracking-wider mb-1">
            Pending Human Review
          </p>
          <div className="flex items-baseline gap-2">
            <span className="font-heading font-bold text-2xl text-ink">
              {pendingCount}
            </span>
            {pendingCount > 0 && (
              <span className="inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-50 text-amber-800 border border-amber-200">
                Action Required
              </span>
            )}
          </div>
          <p className="font-body text-xs text-ink/40 mt-1">
            {completedCount} campaign(s) executed via n8n
          </p>
        </Card>

        {/* Policy Guardrails */}
        <Card className="p-4 bg-white border border-border">
          <p className="font-body text-xs font-medium text-ink/50 uppercase tracking-wider mb-1">
            Policy Guardrail Status
          </p>
          <div className="flex items-baseline gap-1.5">
            <span className="font-heading font-bold text-lg text-ink">
              Max {typeof rules?.max_ai_discount_pct === "number" ? rules.max_ai_discount_pct : 15}% Off
            </span>
          </div>
          <p className="font-body text-xs text-ink/60 mt-1 truncate">
            Approval threshold:{" "}
            {typeof rules?.growth_approval_threshold_amount === "number" &&
            Number.isFinite(rules.growth_approval_threshold_amount)
              ? formatCurrency(rules.growth_approval_threshold_amount)
              : "Always ask (Safe default)"}
          </p>
        </Card>
      </div>

      {/* Catalog Insights Section: Top & Declining Products */}
      {insights && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          {/* Declining Products Alert */}
          <Card className="p-4 bg-white border border-border">
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-heading font-semibold text-ink text-sm flex items-center gap-1.5">
                <TrendingDown className="w-4 h-4 text-coral" />
                Declining Sales Signals
              </h3>
              <Badge variant="surface">{(insights.declining_products ?? []).length} Detected</Badge>
            </div>
            {!(insights.declining_products && insights.declining_products.length > 0) ? (
              <p className="font-body text-xs text-ink/50 py-3">
                No significant product declines detected in the current 14-day window.
              </p>
            ) : (
              <div className="space-y-2 mt-2">
                {insights.declining_products.map((d) => (
                  <div
                    key={d.product_id}
                    className="p-2.5 rounded-lg bg-surface flex items-center justify-between text-xs"
                  >
                    <div>
                      <p className="font-semibold text-ink">{d.product_name || "Product"}</p>
                      <p className="text-ink/50 text-[11px]">
                        Dropped from {formatNumber(d.prior_weekly_units)} to {formatNumber(d.recent_weekly_units)} units/week
                      </p>
                    </div>
                    <span className="font-bold text-coral font-mono">
                      -{typeof d.units_drop_pct === "number" && Number.isFinite(d.units_drop_pct)
                        ? d.units_drop_pct.toFixed(1)
                        : "—"}%
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* Top Selling Products */}
          <Card className="p-4 bg-white border border-border">
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-heading font-semibold text-ink text-sm flex items-center gap-1.5">
                <Package className="w-4 h-4 text-ink/70" />
                Top Revenue Products (14-Day)
              </h3>
              <Badge variant="surface">{(insights.top_products ?? []).length} Products</Badge>
            </div>
            {!(insights.top_products && insights.top_products.length > 0) ? (
              <p className="font-body text-xs text-ink/50 py-3">
                No recent sales recorded in the current window.
              </p>
            ) : (
              <div className="space-y-2 mt-2">
                {insights.top_products.map((p) => (
                  <div
                    key={p.product_id}
                    className="p-2.5 rounded-lg bg-surface flex items-center justify-between text-xs"
                  >
                    <div>
                      <p className="font-semibold text-ink">{p.product_name || "Product"}</p>
                      <p className="text-ink/50 text-[11px]">{formatNumber(p.units_sold)} units sold</p>
                    </div>
                    <span className="font-semibold text-ink">
                      {formatCurrency(p.revenue, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      )}

      {/* Opportunities Section */}
      <div className="mb-4 flex items-center justify-between border-b border-border pb-3">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-ink/70" />
          <h2 className="font-heading font-bold text-ink text-base">Growth Opportunities</h2>
          <span className="text-xs text-ink/40">({opportunities.length} total)</span>
        </div>

        {/* Filter Pills */}
        <div className="flex items-center gap-1 bg-surface p-1 rounded-lg border border-border">
          {[
            { key: "all", label: "All" },
            { key: "pending", label: `Pending (${pendingCount})` },
            { key: "completed", label: `Executed (${completedCount})` },
            { key: "blocked", label: "Blocked" },
          ].map((f) => (
            <button
              key={f.key}
              onClick={() => setSelectedFilter(f.key)}
              className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                selectedFilter === f.key
                  ? "bg-white text-ink shadow-sm border border-border/50"
                  : "text-ink/60 hover:text-ink"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Opportunity Cards List */}
      {oppsError ? (
        <Card className="p-8 text-center bg-white border border-border">
          <div className="flex flex-col items-center justify-center max-w-md mx-auto">
            <AlertCircle size={24} className="text-coral mb-2" />
            <h3 className="font-heading font-semibold text-sm text-ink mb-1">
              Failed to load opportunities
            </h3>
            <p className="font-body text-xs text-ink/60 mb-4">{oppsError}</p>
            <Button variant="outline" size="sm" onClick={loadData}>
              Retry Loading Opportunities
            </Button>
          </div>
        </Card>
      ) : filteredOpps.length === 0 ? (
        <Card className="p-8 text-center bg-white border border-border">
          <p className="font-body text-sm text-ink/50 mb-3">
            No growth opportunities match the selected filter.
          </p>
          <Button variant="outline" size="sm" onClick={handleScan} disabled={scanning}>
            Run New Opportunity Scan
          </Button>
        </Card>
      ) : (
        <div className="space-y-4">
          {filteredOpps.map((opp) => (
            <OpportunityCard
              key={opp.id}
              opportunity={opp}
              onApprove={handleApprove}
              onReject={handleReject}
            />
          ))}
        </div>
      )}
    </div>
  );
}
