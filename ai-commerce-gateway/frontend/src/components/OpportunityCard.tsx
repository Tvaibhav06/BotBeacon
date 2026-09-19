import React, { useState } from "react";
import {
  ShieldAlert,
  ShieldCheck,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
  ArrowRight,
  TrendingDown,
  Sparkles,
  Zap,
} from "lucide-react";
import { GrowthOpportunity, GrowthRecommendedAction } from "../lib/api";
import { formatNumber, formatCurrency, formatDate } from "../lib/formatters";
import { Card } from "../design-system/Card";
import { Button } from "../design-system/Button";
import { Badge } from "../design-system/Badge";

interface OpportunityCardProps {
  opportunity: GrowthOpportunity;
  onApprove?: (id: string) => Promise<void>;
  onReject?: (id: string) => Promise<void>;
}

export function OpportunityCard({
  opportunity,
  onApprove,
  onReject,
}: OpportunityCardProps) {
  const [approving, setApproving] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const {
    id = "",
    title = "",
    opportunity_type = "declining_sales",
    evidence = {} as Record<string, unknown>,
    recommended_action = {} as GrowthRecommendedAction,
    estimated_discount_exposure,
    policy_outcome = "blocked",
    policy_reasons = [],
    status = "new",
  } = opportunity || {};

  const isPending = status === "pending_approval";
  const isBlocked = status === "blocked" || policy_outcome === "blocked";
  const isExecuting = status === "executing";
  const isCompleted = status === "completed";
  const isRejected = status === "rejected_by_merchant";

  const handleApprove = async () => {
    if (!onApprove) return;
    setApproving(true);
    setActionError(null);
    try {
      await onApprove(id);
    } catch (err: any) {
      setActionError(err.message || "Failed to approve opportunity");
    } finally {
      setApproving(false);
    }
  };

  const handleReject = async () => {
    if (!onReject) return;
    setRejecting(true);
    setActionError(null);
    try {
      await onReject(id);
    } catch (err: any) {
      setActionError(err.message || "Failed to reject opportunity");
    } finally {
      setRejecting(false);
    }
  };

  return (
    <Card className="border border-border hover:border-ink/20 transition-all p-5 shadow-sm bg-white">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2 mb-3">
        <div>
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className="font-mono text-xs text-ink/40 font-medium">#{id}</span>
            <Badge variant="surface">
              {opportunity_type === "declining_sales" ? (
                <span className="flex items-center gap-1">
                  <TrendingDown className="w-3 h-3 text-coral" /> Declining Sales
                </span>
              ) : (
                <span className="flex items-center gap-1">
                  <Sparkles className="w-3 h-3 text-ink" /> Cross-Sell Gap
                </span>
              )}
            </Badge>

            {/* Policy Outcome Pill */}
            {policy_outcome === "blocked" && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-coral/10 text-coral border border-coral/20">
                <ShieldAlert className="w-3 h-3" /> Blocked by Policy
              </span>
            )}
            {policy_outcome === "requires_approval" && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-800 border border-amber-200">
                <Clock className="w-3 h-3 text-amber-600" /> Requires Approval
              </span>
            )}
            {policy_outcome === "allowed" && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-lime/20 text-ink border border-lime/40">
                <ShieldCheck className="w-3 h-3" /> Autonomous Allowed
              </span>
            )}

            {/* Execution / Lifecycle status */}
            {isExecuting && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200 animate-pulse">
                <Zap className="w-3 h-3" /> Executing in n8n...
              </span>
            )}
            {isCompleted && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200">
                <CheckCircle2 className="w-3 h-3 text-emerald-600" /> Executed (Completed)
              </span>
            )}
            {isRejected && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-surface text-ink/50 border border-border">
                <XCircle className="w-3 h-3" /> Rejected
              </span>
            )}
          </div>
          <h3 className="font-heading font-semibold text-ink text-base">{title}</h3>
        </div>

        {/* Estimated Exposure Pill */}
        <div className="text-right sm:shrink-0 bg-surface/80 border border-border px-3 py-1.5 rounded-lg">
          <p className="font-body text-[11px] text-ink/50 uppercase tracking-wider font-medium">
            Est. Discount Exposure
          </p>
          <p className="font-heading font-bold text-ink text-base">
            {formatCurrency(estimated_discount_exposure, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </p>
        </div>
      </div>

      {/* Recommended Action & Evidence */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 my-3 text-xs bg-surface/50 p-3 rounded-lg border border-border/60">
        <div>
          <p className="font-semibold text-ink/70 mb-1 uppercase tracking-wider text-[10px]">
            Action Details
          </p>
          <p className="text-ink font-medium">
            Type: <span className="text-ink/70 font-normal">{recommended_action?.type ? String(recommended_action.type) : "discount_bundle"}</span>
          </p>
          <p className="text-ink font-medium">
            Discount:{" "}
            <span className="text-ink/70 font-normal">
              {typeof recommended_action?.discount_pct === "number" && Number.isFinite(recommended_action.discount_pct)
                ? `${recommended_action.discount_pct}% off`
                : "—"}
            </span>
          </p>
          <p className="text-ink font-medium">
            Duration:{" "}
            <span className="text-ink/70 font-normal">
              {typeof recommended_action?.campaign_duration_weeks === "number" && Number.isFinite(recommended_action.campaign_duration_weeks)
                ? `${recommended_action.campaign_duration_weeks} week(s)`
                : "—"}
            </span>
          </p>
          <p className="text-ink font-medium">
            Audience:{" "}
            <span className="text-ink/70 font-normal">
              {recommended_action?.audience ? String(recommended_action.audience) : "Configured Demo Audience"}
            </span>
          </p>
        </div>

        <div>
          <p className="font-semibold text-ink/70 mb-1 uppercase tracking-wider text-[10px]">
            Supporting Evidence
          </p>
          {opportunity_type === "declining_sales" ? (
            <div>
              <p className="text-ink font-medium">
                Trend:{" "}
                <span className="text-coral font-semibold">
                  {typeof evidence?.units_drop_pct === "number" && Number.isFinite(evidence.units_drop_pct)
                    ? `-${evidence.units_drop_pct.toFixed(1)}% drop`
                    : "Declining sales volume"}
                </span>
              </p>
              <p className="text-ink/70">
                Units: {formatNumber(evidence?.recent_weekly_units as number | undefined)} recent / {formatNumber(evidence?.prior_weekly_units as number | undefined)} prior weekly
              </p>
              <p className="text-ink/70">
                Primary: {evidence?.product_name ? String(evidence.product_name) : "Velocity Pro"}
              </p>
            </div>
          ) : (
            <div>
              <p className="text-ink font-medium">
                Attach Rate:{" "}
                <span className="text-amber-700 font-semibold">
                  {typeof evidence?.attach_rate_pct === "number" && Number.isFinite(evidence.attach_rate_pct)
                    ? `${evidence.attach_rate_pct}%`
                    : evidence?.attach_rate_pct != null
                    ? `${String(evidence.attach_rate_pct)}%`
                    : "—"}
                </span>
              </p>
              <p className="text-ink/70">
                Primary: {evidence?.primary_product_name ? String(evidence.primary_product_name) : "Velocity Pro"}
              </p>
              <p className="text-ink/70">
                Complement: {evidence?.complement_product_name ? String(evidence.complement_product_name) : "Performance Socks"}
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Policy Reasons & Alerts */}
      {Array.isArray(policy_reasons) && policy_reasons.length > 0 && (
        <div className="mb-3 text-xs">
          {isBlocked ? (
            <div className="bg-coral/5 border border-coral/20 text-coral p-2.5 rounded-lg flex items-start gap-2">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold">Blocked by Policy Gate:</p>
                <ul className="list-disc pl-4 mt-0.5 space-y-0.5">
                  {policy_reasons.map((r, i) => (
                    <li key={i}>{typeof r === "string" ? r : JSON.stringify(r)}</li>
                  ))}
                </ul>
              </div>
            </div>
          ) : (
            <div className="text-ink/60 bg-surface px-3 py-1.5 rounded-md border border-border">
              <span className="font-medium text-ink/80">Policy Note:</span>{" "}
              {policy_reasons.map((r) => (typeof r === "string" ? r : JSON.stringify(r))).join("; ")}
            </div>
          )}
        </div>
      )}

      {/* Action Error Banner */}
      {actionError && (
        <div className="mb-3 p-2.5 rounded-lg bg-coral/10 border border-coral/30 text-coral text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{actionError}</span>
        </div>
      )}

      {/* Action Buttons: Shown ONLY when status === 'pending_approval' and NOT blocked */}
      {isPending && !isBlocked && (
        <div className="flex items-center justify-end gap-2 pt-2 border-t border-border mt-3">
          <Button
            variant="outline"
            size="sm"
            onClick={handleReject}
            disabled={rejecting || approving}
            className="text-ink/60 hover:text-coral hover:border-coral"
          >
            {rejecting ? "Rejecting..." : "Reject"}
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={handleApprove}
            disabled={approving || rejecting}
            className="bg-lime text-ink hover:bg-lime/90 font-medium"
          >
            {approving ? (
              "Verifying Policy & Triggering n8n..."
            ) : (
              <span className="flex items-center gap-1">
                Approve & Execute <ArrowRight className="w-3.5 h-3.5" />
              </span>
            )}
          </Button>
        </div>
      )}
    </Card>
  );
}
