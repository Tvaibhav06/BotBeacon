import React, { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { Filter, ArrowRight, AlertCircle, RefreshCw } from "lucide-react";
import { api, AuditLogEntry, ApiError } from "../lib/api";
import { useAuth } from "../lib/AuthContext";
import { formatDate } from "../lib/formatters";
import { Card } from "../design-system/Card";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";

const STAGES = [
  "passport_activated",
  "decision_engine",
  "mandate_check",
  "policy_gate",
  "payment",
  "verification",
  "growth_analysis",
  "growth_approval",
  "growth_execution",
];

export function AuditLogPage() {
  const { token, merchantId } = useAuth();
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedStage, setSelectedStage] = useState<string>("");

  const loadLogs = useCallback(() => {
    if (!merchantId || !token) return;
    setLoading(true);
    setError(null);
    api
      .getAuditLog(merchantId, token, selectedStage || undefined)
      .then((data) => {
        setLogs(Array.isArray(data) ? data : []);
        setError(null);
      })
      .catch((e: unknown) => {
        setLogs([]);
        if (e instanceof ApiError) {
          if (e.isUnauthorized) {
            setError("Authentication session expired or invalid. Please sign in again.");
          } else if (e.isForbidden) {
            setError("Access denied: You are not authorized to view audit logs for this merchant.");
          } else if (e.isNetworkError) {
            setError("Network connection failure: Unable to reach backend service. Please check your network connection.");
          } else if (e.isServerError) {
            setError(`Failed to load audit logs: Internal server error (HTTP ${e.status}).`);
          } else {
            setError(e.detail || e.message || `API error (HTTP ${e.status})`);
          }
        } else {
          setError(e instanceof Error ? e.message : "Failed to load audit logs");
        }
      })
      .finally(() => setLoading(false));
  }, [merchantId, token, selectedStage]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  if (loading && logs.length === 0 && !error) {
    return (
      <div className="p-8">
        <h1 className="font-heading text-2xl font-bold text-ink mb-2">Audit Log</h1>
        <p className="font-body text-sm text-ink/50 flex items-center gap-2">
          <RefreshCw className="animate-spin" size={16} /> Loading logs…
        </p>
      </div>
    );
  }

  return (
    <div className="p-8 max-w-6xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-heading text-2xl font-bold text-ink">Audit Log</h1>
          <p className="font-body text-sm text-ink/50 mt-0.5">
            Immutable, append-only ledger of all system, AI, and merchant actions.
          </p>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Filter size={16} className="text-ink/40" />
            <select
              value={selectedStage}
              onChange={(e) => setSelectedStage(e.target.value)}
              className="font-body text-sm text-ink border border-border rounded-lg px-3 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-ink/20"
            >
              <option value="">All Stages</option>
              {STAGES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <Button variant="outline" size="sm" onClick={loadLogs} disabled={loading}>
            <RefreshCw className={`mr-1.5 ${loading ? "animate-spin" : ""}`} size={14} />
            Refresh
          </Button>
        </div>
      </div>

      {error ? (
        <Card className="p-8 text-center bg-white border border-border">
          <div className="flex flex-col items-center justify-center max-w-md mx-auto">
            <div className="w-10 h-10 rounded-full bg-coral/10 flex items-center justify-center text-coral mb-3">
              <AlertCircle size={20} />
            </div>
            <h3 className="font-heading font-semibold text-ink text-base mb-1">
              Failed to load audit logs
            </h3>
            <p className="font-body text-xs text-ink/60 mb-4 leading-relaxed">{error}</p>
            <Button variant="outline" size="sm" onClick={loadLogs}>
              Retry
            </Button>
          </div>
        </Card>
      ) : logs.length === 0 ? (
        <Card className="p-8 text-center bg-white border border-border">
          <p className="font-body text-sm text-ink/50 py-4">
            No audit logs found.
          </p>
        </Card>
      ) : (
        <div className="border border-border rounded-2xl overflow-hidden bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface border-b border-border">
                <th className="text-left font-body font-semibold text-ink/60 px-4 py-3 w-48">Timestamp</th>
                <th className="text-left font-body font-semibold text-ink/60 px-4 py-3">Actor</th>
                <th className="text-left font-body font-semibold text-ink/60 px-4 py-3">Stage</th>
                <th className="text-left font-body font-semibold text-ink/60 px-4 py-3">Transaction</th>
                <th className="text-left font-body font-semibold text-ink/60 px-4 py-3">Payload Summary</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log, i) => {
                const isLast = i === logs.length - 1;
                return (
                  <tr
                    key={log.id}
                    className={`hover:bg-surface/60 transition-colors ${!isLast ? "border-b border-border" : ""}`}
                  >
                    <td className="px-4 py-3 font-mono text-xs text-ink/50 whitespace-nowrap">
                      {formatDate(log.timestamp)}
                    </td>
                    <td className="px-4 py-3 font-body text-xs text-ink/70">
                      <Badge variant="surface">{log.actor}</Badge>
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-ink">
                      {log.stage}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">
                      {log.transaction_id ? (
                        <Link 
                          to={`/transactions/${log.transaction_id}/audit`}
                          className="text-ink hover:underline flex items-center gap-1"
                        >
                          {log.transaction_id.slice(0, 12)}...
                          <ArrowRight size={12} className="text-ink/40" />
                        </Link>
                      ) : (
                        <span className="text-ink/30">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-ink/60 max-w-xs truncate">
                      {JSON.stringify(log.payload)}
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
