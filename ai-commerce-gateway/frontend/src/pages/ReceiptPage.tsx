import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, Loader2 } from "lucide-react";
import { DecisionReceipt as ReceiptType, api } from "../lib/api";
import { DecisionReceipt } from "../components/DecisionReceipt";
import { Card } from "../design-system/Card";

export function ReceiptPage() {
  const { id } = useParams<{ id: string }>();
  const [receipt, setReceipt] = useState<ReceiptType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    
    api.getReceipt(id)
      .then(data => {
        setReceipt(data);
        setError(null);
      })
      .catch(err => {
        console.error(err);
        setError("Failed to load receipt or not found.");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [id]);

  return (
    <div className="max-w-4xl mx-auto p-4 md:p-8">
      <Link
        to="/transactions"
        className="inline-flex items-center gap-1 font-body text-sm text-ink/50 hover:text-ink transition-colors mb-6"
      >
        <ArrowLeft size={14} /> Back to Transactions
      </Link>

      {loading ? (
        <Card className="py-24 flex flex-col items-center justify-center">
          <Loader2 className="animate-spin text-ink/40 mb-4" size={32} />
          <p className="font-heading text-ink/60">Loading receipt...</p>
        </Card>
      ) : error || !receipt ? (
        <Card className="py-24 flex flex-col items-center justify-center">
          <p className="font-heading text-coral text-lg mb-2">Error Loading Receipt</p>
          <p className="text-ink/60 font-body text-sm">{error || "Receipt not found."}</p>
        </Card>
      ) : (
        <div className="max-w-2xl mx-auto">
          <DecisionReceipt receipt={receipt} />
        </div>
      )}
    </div>
  );
}
