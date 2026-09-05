import React, { useState } from "react";
import { Link } from "react-router-dom";
import { Play, CheckCircle2, Circle, AlertCircle, RefreshCw, XCircle } from "lucide-react";
import { DecisionReceipt as ReceiptType } from "../lib/api";
import { useRazorpayCheckout } from "../lib/useRazorpayCheckout";
import { useAuth } from "../lib/AuthContext";
import { DecisionReceipt } from "../components/DecisionReceipt";
import { Card } from "../design-system/Card";
import { Badge } from "../design-system/Badge";

type FlowStage = "idle" | "decision_engine" | "mandate_check" | "policy_gate" | "payment" | "verification" | "done";

export function SimulatorPage() {
  const { token } = useAuth();
  const { openCheckout } = useRazorpayCheckout();
  const [intent, setIntent] = useState("Find me running shoes under 6000");
  const [isRunning, setIsRunning] = useState(false);
  const [currentStage, setCurrentStage] = useState<FlowStage>("idle");
  const [logs, setLogs] = useState<string[]>([]);
  const [receipt, setReceipt] = useState<ReceiptType | null>(null);
  const [isBlocked, setIsBlocked] = useState(false);

  const presets = [
    "Find me running shoes under 6000",
    "Buy the 8999 Velocity Pro Premium footwear",
  ];

  const handleRun = async () => {
    if (!intent.trim() || isRunning) return;
    
    setIsRunning(true);
    setCurrentStage("decision_engine");
    setLogs([]);
    setReceipt(null);
    setIsBlocked(false);

    try {
      const response = await fetch("/api/demo/buyer-request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ intent }),
      });

      if (!response.ok) throw new Error("Failed to start simulation");
      if (!response.body) throw new Error("No response body");

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || ""; // Keep the incomplete chunk in the buffer

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.substring(6));
              
              if (data.type === "log") {
                const msg = data.message;
                setLogs((prev) => [...prev, msg]);

                // Update stage based on log keywords
                if (msg.includes("[buyer] Building cart")) setCurrentStage("mandate_check");
                if (msg.includes("[buyer] Checking policy")) setCurrentStage("policy_gate");
                if (msg.includes("[buyer] Checkout")) setCurrentStage("payment");
                if (msg.includes("BLOCKED")) setIsBlocked(true);

              } else if (data.type === "receipt") {
                const r = data.data;
                setReceipt(r);
                if (r._transaction_status === "pending_payment" && r._razorpay_order_id) {
                  if (token) {
                    openCheckout({
                      razorpay_order_id: r._razorpay_order_id,
                      amount: r.final_total,
                      transaction_id: r.transaction_id,
                      token: token,
                      onVerified: (res) => {
                        console.log("Verified:", res);
                        setCurrentStage("verification");
                        setTimeout(() => setCurrentStage("done"), 1000);
                      },
                      onDismissed: () => {
                        console.log("Dismissed");
                        setCurrentStage("done");
                      }
                    });
                  } else {
                    console.warn("No token available for checkout");
                    setCurrentStage("done");
                  }
                } else {
                  setCurrentStage("done");
                }
              }
            } catch (err) {
              console.error("Failed to parse SSE line", err);
            }
          }
        }
      }
    } catch (err) {
      console.error(err);
      setLogs((prev) => [...prev, "ERROR: Connection lost or failed to parse response."]);
      setCurrentStage("done");
    } finally {
      setIsRunning(false);
    }
  };

  const getStageVisual = (stageId: FlowStage, label: string) => {
    const stages: FlowStage[] = ["decision_engine", "mandate_check", "policy_gate", "payment", "verification", "done"];
    
    const currentIndex = stages.indexOf(currentStage === "idle" ? "decision_engine" : currentStage);
    const thisIndex = stages.indexOf(stageId);
    
    let status: "pending" | "active" | "completed" | "blocked" = "pending";
    
    if (currentStage === "idle") {
      status = "pending";
    } else if (thisIndex < currentIndex || currentStage === "done") {
      if (isBlocked && stageId === "payment") {
         status = "blocked";
      } else if (isBlocked && stageId === "verification") {
         status = "pending"; // never reached
      } else {
         status = "completed";
      }
    } else if (thisIndex === currentIndex) {
      status = "active";
    }

    return (
      <div className="flex flex-col items-center justify-center gap-2 flex-1 relative">
        <div className={`z-10 bg-surface flex items-center justify-center rounded-full p-1 transition-colors ${
          status === "active" ? "text-blue-400" :
          status === "completed" ? "text-lime" :
          status === "blocked" ? "text-coral" :
          "text-ink/20"
        }`}>
          {status === "active" ? <RefreshCw className="animate-spin" size={24} /> :
           status === "completed" ? <CheckCircle2 size={24} /> :
           status === "blocked" ? <XCircle size={24} /> :
           <Circle size={24} />}
        </div>
        <span className={`text-[10px] uppercase font-semibold tracking-wider text-center max-w-[80px] ${
           status === "active" ? "text-blue-400" :
           status === "completed" ? "text-lime" :
           status === "blocked" ? "text-coral" :
           "text-ink/30"
        }`}>
          {label}
        </span>
      </div>
    );
  };

  return (
    <div className="max-w-6xl mx-auto p-4 md:p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="font-heading text-2xl font-bold text-ink">Buyer Simulator</h1>
          <p className="font-body text-sm text-ink/50 mt-1">
            Test the AI Commerce Gateway end-to-end. Watch deterministic guardrails enforce policy live.
          </p>
        </div>
      </div>

      <div className="grid lg:grid-cols-12 gap-8">
        
        {/* LEFT COLUMN: Controls & Rules */}
        <div className="lg:col-span-5 space-y-6">
          <Card className="p-6 space-y-4">
            <h2 className="font-heading font-semibold text-lg border-b border-border pb-2 mb-4">Input Prompt</h2>
            <textarea
              className="w-full bg-surface border border-border rounded-lg p-3 text-sm min-h-[100px] resize-none focus:outline-none focus:border-ink/30 transition-colors"
              placeholder="e.g. Find me running shoes under 6000"
              value={intent}
              onChange={(e) => setIntent(e.target.value)}
              disabled={isRunning}
            />
            
            <div className="flex flex-wrap gap-2 pt-2">
              {presets.map((p, idx) => (
                <button
                  key={idx}
                  onClick={() => setIntent(p)}
                  disabled={isRunning}
                  className="text-xs bg-surface border border-border px-3 py-1.5 rounded-full hover:border-ink/30 transition-colors text-left"
                >
                  {p}
                </button>
              ))}
            </div>

            <button
              onClick={handleRun}
              disabled={isRunning || !intent.trim()}
              className="w-full bg-ink text-white font-body font-medium rounded-lg py-3 flex items-center justify-center gap-2 hover:bg-ink/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed mt-4"
            >
              {isRunning ? <RefreshCw className="animate-spin" size={18} /> : <Play size={18} />}
              {isRunning ? "Running Flow..." : "Run Simulation"}
            </button>
          </Card>

          <Card className="p-6 bg-surface/50 border border-border">
             <div className="flex items-center justify-between mb-4">
               <h3 className="font-heading font-semibold text-sm">Active Rules Context</h3>
               <Badge variant="ink">Global</Badge>
             </div>
             <div className="space-y-3 text-sm">
               <div className="flex justify-between border-b border-border/50 pb-2">
                 <span className="text-ink/60">Buyer Mandate Limit</span>
                 <span className="font-mono font-medium">₹6,000</span>
               </div>
               <div className="flex justify-between border-b border-border/50 pb-2">
                 <span className="text-ink/60">Merchant Max AI Discount</span>
                 <span className="font-mono font-medium">0%</span>
               </div>
               <div className="flex justify-between">
                 <span className="text-ink/60">Merchant Minimum Margin</span>
                 <span className="font-mono font-medium">10%</span>
               </div>
             </div>
             <p className="text-xs text-ink/40 mt-4 flex items-start gap-1.5 leading-snug">
               <AlertCircle size={14} className="shrink-0" />
               The Decision Engine runs on Gemini, but the Mandate Check and Policy Gate execute deterministically via MCP tools on the Gateway backend.
             </p>
          </Card>

          {/* FLOW TRACKER */}
          <Card className="p-6">
            <h3 className="font-heading font-semibold text-sm mb-6 text-center text-ink/70">Transaction Flow</h3>
            <div className="relative flex justify-between">
              {/* Connector Line */}
              <div className="absolute top-[16px] left-[10%] right-[10%] h-[2px] bg-border z-0" />
              
              {getStageVisual("decision_engine", "AI Decision")}
              {getStageVisual("mandate_check", "Mandate Check")}
              {getStageVisual("policy_gate", "Policy Gate")}
              {getStageVisual("payment", "Checkout")}
            </div>
            
            {/* Verification is separate since it happens post-Razorpay */}
            {receipt && !isBlocked && (
              <div className="mt-6 pt-4 border-t border-border flex justify-center">
                 {getStageVisual("verification", "Verification")}
              </div>
            )}
          </Card>
        </div>

        {/* RIGHT COLUMN: Output & Logs */}
        <div className="lg:col-span-7 flex flex-col gap-6">
          {/* Decision Receipt Area */}
          <div className="min-h-[300px]">
             {receipt ? (
               <DecisionReceipt receipt={receipt} />
             ) : (
               <div className="h-full flex flex-col items-center justify-center border border-dashed border-border rounded-2xl bg-surface/30 p-12 text-center text-ink/40">
                 <CheckCircle2 size={48} className="mb-4 opacity-20" />
                 <p className="font-heading font-medium text-lg text-ink/60 mb-2">Awaiting Simulation</p>
                 <p className="text-sm max-w-sm">Enter a prompt and click Run to watch the AI buyer negotiate the merchant's guardrails in real-time.</p>
               </div>
             )}
          </div>

          {/* Live Terminal Output */}
          <Card className="flex-1 bg-[#1A1A1A] text-white/90 p-4 font-mono text-xs overflow-hidden flex flex-col h-[400px]">
             <div className="flex items-center justify-between mb-3 border-b border-white/10 pb-2">
               <span className="text-white/40 uppercase tracking-widest text-[10px]">Live Flow Output</span>
               {isRunning && <span className="flex items-center gap-1.5 text-lime"><span className="w-2 h-2 bg-lime rounded-full animate-pulse" /> Streaming</span>}
             </div>
             <div className="flex-1 overflow-y-auto space-y-1.5 scrollbar-thin scrollbar-thumb-white/10 pr-2">
               {logs.length === 0 && !isRunning && (
                 <span className="text-white/30 italic">No output yet...</span>
               )}
               {logs.map((log, i) => (
                 <div key={i} className={`whitespace-pre-wrap ${log.includes("ERROR") || log.includes("BLOCKED") || log.includes("✗") ? "text-coral" : log.includes("✓") ? "text-lime" : ""}`}>
                   {log}
                 </div>
               ))}
             </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
