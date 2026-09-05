import React, { useEffect, useState, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, CheckCircle2, XCircle, Clock } from "lucide-react";
import { api, AuditLogEntry } from "../lib/api";
import { useAuth } from "../lib/AuthContext";
import { Card } from "../design-system/Card";
import { Badge } from "../design-system/Badge";

export function TransactionAuditPage() {
  const { id } = useParams<{ id: string }>();
  const { token } = useAuth();
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadLogs = useCallback(() => {
    if (!id || !token) return;
    setLoading(true);
    setError(null);
    api
      .getAuditTrail(id, token)
      .then(setLogs)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load audit trail"))
      .finally(() => setLoading(false));
  }, [id, token]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  if (loading && logs.length === 0) {
    return (
      <div className="p-8">
        <h1 className="font-heading text-2xl font-bold text-ink mb-2">Transaction Audit Trail</h1>
        <p className="font-body text-sm text-ink/50">Loading timeline…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <div className="mb-4 bg-coral/10 border border-coral/30 rounded-xl px-4 py-4">
          <span className="font-body text-sm text-coral">{error}</span>
        </div>
      </div>
    );
  }

  // Helper to render payload/result blocks cleanly
  const renderJsonBlock = (title: string, data: Record<string, unknown>) => {
    if (!data || Object.keys(data).length === 0) return null;
    return (
      <div className="mt-2 bg-surface/50 rounded-lg p-3 border border-border/50">
        <p className="font-body text-xs font-semibold text-ink/60 mb-1">{title}</p>
        <pre className="font-mono text-[10px] sm:text-xs text-ink/70 whitespace-pre-wrap overflow-x-auto">
          {JSON.stringify(data, null, 2)}
        </pre>
      </div>
    );
  };

  return (
    <div className="p-8 max-w-4xl">
      <Link
        to="/transactions"
        className="inline-flex items-center gap-1 font-body text-sm text-ink/50 hover:text-ink transition-colors mb-6"
      >
        <ArrowLeft size={14} /> Back to Transactions
      </Link>

      <div className="mb-8">
        <h1 className="font-heading text-2xl font-bold text-ink">Transaction Journey</h1>
        <p className="font-body text-sm text-ink/50 mt-1">
          ID: <span className="font-mono">{id}</span>
        </p>
      </div>

      {logs.length === 0 ? (
        <Card>
          <p className="font-body text-sm text-ink/50 text-center py-8">
            No logs found for this transaction.
          </p>
        </Card>
      ) : (
        <div className="relative pl-6">
          {/* Timeline line */}
          <div className="absolute top-0 bottom-0 left-[15px] w-[2px] bg-border" />
          
          <div className="flex flex-col gap-6">
            {logs.map((log, index) => {
              const isLast = index === logs.length - 1;
              // Determine status visual from the log
              let isSuccess = true;
              if (log.stage === "mandate_check" || log.stage === "policy_gate") {
                isSuccess = (log.result as any)?.passed === true;
              } else if (log.stage === "verification") {
                isSuccess = (log.result as any)?.match === true;
              }

              return (
                <div key={log.id} className="relative">
                  {/* Timeline dot */}
                  <div 
                    className={`absolute -left-6 top-1 w-[10px] h-[10px] rounded-full ring-4 ring-white ${
                      isSuccess ? "bg-lime" : "bg-coral"
                    }`} 
                  />

                  <Card className="ml-2 shadow-sm border border-border/50">
                    <div className="flex flex-wrap items-start justify-between gap-4 mb-3">
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="font-heading text-base font-semibold text-ink">
                            {log.stage}
                          </h3>
                          <Badge variant={log.actor === "system" ? "ink" : "surface"}>
                            {log.actor}
                          </Badge>
                        </div>
                        <p className="font-mono text-xs text-ink/40">
                          {new Date(log.timestamp).toLocaleString()}
                        </p>
                      </div>
                      
                      {/* Success/Fail icon for gate stages */}
                      {(log.stage === "mandate_check" || log.stage === "policy_gate" || log.stage === "verification") && (
                        <div className={`flex items-center gap-1 font-body text-xs font-medium px-2 py-1 rounded-full ${
                          isSuccess ? "bg-lime/20 text-ink" : "bg-coral/10 text-coral"
                        }`}>
                          {isSuccess ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
                          {isSuccess ? "Passed" : "Failed"}
                        </div>
                      )}
                    </div>

                    <div className="grid sm:grid-cols-2 gap-4">
                      {renderJsonBlock("Payload (Input)", log.payload)}
                      {renderJsonBlock("Result (Output)", log.result)}
                    </div>
                  </Card>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
