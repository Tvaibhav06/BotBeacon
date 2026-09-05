import React from "react";
import { CheckCircle2, XCircle } from "lucide-react";
import { DecisionReceipt as ReceiptType } from "../lib/api";

export function DecisionReceipt({ receipt }: { receipt: ReceiptType }) {
  // Determine block status based on authorization and payment status
  const isBlocked =
    receipt.authorization_status.toLowerCase().includes("blocked") ||
    receipt.payment_status.toLowerCase().includes("never called") ||
    receipt.payment_status.toLowerCase().includes("failed");

  return (
    <div className="bg-ink rounded-2xl p-6 md:p-8 text-white shadow-2xl overflow-hidden font-body relative">
      {/* Decorative top edge */}
      <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-lime to-lime/30" />

      <h2 className="font-heading text-xs tracking-widest text-white/50 mb-8 uppercase">
        AI Commerce Decision Receipt
      </h2>

      {/* ── Request ── */}
      <div className="mb-8">
        <h3 className="text-[10px] uppercase tracking-wider text-white/40 mb-1">Request</h3>
        <p className="text-lg md:text-xl font-medium leading-snug">
          "{receipt.customer_request}"
        </p>
      </div>

      {/* Render details only if not completely blocked before AI could decide */}
      {(!isBlocked || receipt.selected) && (
        <div className="space-y-6 mb-8">
          {/* ── Considered ── */}
          {receipt.ai_considered_count != null && (
            <div className="grid grid-cols-[100px_1fr] items-baseline">
              <span className="text-[10px] uppercase tracking-wider text-white/40">Considered</span>
              <span className="text-sm">{receipt.ai_considered_count} products</span>
            </div>
          )}

          {/* ── Selected ── */}
          {receipt.selected && (
            <div className="grid grid-cols-[100px_1fr] items-start">
              <span className="text-[10px] uppercase tracking-wider text-white/40 mt-1">Selected</span>
              <div>
                <span className="block text-base font-medium">{receipt.selected.product_id}</span>
                <span className="block text-sm text-lime">₹{receipt.selected.unit_price.toLocaleString("en-IN")}</span>
              </div>
            </div>
          )}

          {/* ── Why ── */}
          {receipt.why && receipt.why.length > 0 && (
            <div className="grid grid-cols-[100px_1fr] items-start">
              <span className="text-[10px] uppercase tracking-wider text-white/40 mt-1">Why</span>
              <ul className="space-y-2">
                {receipt.why.map((reason, idx) => (
                  <li key={idx} className="flex items-start gap-2 text-sm text-white/80">
                    <CheckCircle2 size={16} className="text-lime shrink-0 mt-0.5" />
                    <span className="leading-snug">{reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* ── Upsell ── */}
          {receipt.upsell && (
            <div className="grid grid-cols-[100px_1fr] items-start border-t border-white/10 pt-6">
              <span className="text-[10px] uppercase tracking-wider text-white/40 mt-1">Upsell</span>
              <div>
                <span className="block text-sm font-medium">{receipt.upsell.product_id}</span>
                <span className="block text-xs text-white/60 mb-1">Highest-value eligible complement</span>
                <span className="block text-sm text-lime">₹{receipt.upsell.unit_price.toLocaleString("en-IN")}</span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Final Total ── */}
      <div className="border-t border-white/10 pt-6 pb-6 mb-6">
        <div className="flex items-end justify-between">
          <span className="text-[10px] uppercase tracking-wider text-white/40 pb-2">Final</span>
          <span className="font-heading text-4xl md:text-5xl font-bold text-lime">
            ₹{receipt.final_total.toLocaleString("en-IN")}
          </span>
        </div>
      </div>

      {/* ── Status Section ── */}
      <div className="space-y-3 bg-white/5 rounded-xl p-4">
        {/* Authorization Status */}
        <div className="flex items-start gap-3">
          <span className="w-24 text-[10px] uppercase tracking-wider text-white/40 shrink-0 mt-1">
            Authorization
          </span>
          <div className="flex items-start gap-1.5 flex-1">
            {receipt.authorization_status.toLowerCase().includes("blocked") ? (
              <XCircle size={14} className="text-coral shrink-0 mt-0.5" />
            ) : (
              <CheckCircle2 size={14} className="text-lime shrink-0 mt-0.5" />
            )}
            <span className={`text-sm leading-snug font-medium ${
              receipt.authorization_status.toLowerCase().includes("blocked") ? "text-coral" : "text-white"
            }`}>
              {receipt.authorization_status}
            </span>
          </div>
        </div>

        {/* Payment Status */}
        <div className="flex items-start gap-3">
          <span className="w-24 text-[10px] uppercase tracking-wider text-white/40 shrink-0 mt-1">
            Payment
          </span>
          <div className="flex items-start gap-1.5 flex-1">
            {receipt.payment_status.toLowerCase().includes("never called") || receipt.payment_status.toLowerCase().includes("failed") ? (
              <XCircle size={14} className="text-coral shrink-0 mt-0.5" />
            ) : (
              <CheckCircle2 size={14} className="text-lime shrink-0 mt-0.5" />
            )}
            <span className={`text-sm leading-snug font-medium ${
              (receipt.payment_status.toLowerCase().includes("never called") || receipt.payment_status.toLowerCase().includes("failed")) ? "text-coral" : "text-white"
            }`}>
              {receipt.payment_status}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
