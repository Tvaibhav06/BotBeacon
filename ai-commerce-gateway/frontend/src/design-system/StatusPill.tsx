import React from "react";
import { CheckCircle, XCircle, Clock, AlertCircle } from "lucide-react";

type StatusVariant = "approved" | "blocked" | "pending" | "warning";

interface StatusPillProps {
  status: StatusVariant;
  label?: string;
  className?: string;
}

const config: Record<StatusVariant, { icon: React.ElementType; textClass: string; label: string }> = {
  approved: { icon: CheckCircle, textClass: "text-ink", label: "Approved" },
  blocked: { icon: XCircle, textClass: "text-coral", label: "Blocked" },
  pending: { icon: Clock, textClass: "text-ink/60", label: "Pending" },
  warning: { icon: AlertCircle, textClass: "text-ink/70", label: "Warning" },
};

export function StatusPill({ status, label, className = "" }: StatusPillProps) {
  const { icon: Icon, textClass, label: defaultLabel } = config[status];
  return (
    <span
      className={[
        "inline-flex items-center gap-1.5 font-body font-medium text-sm",
        textClass,
        className,
      ].join(" ")}
    >
      <Icon className="w-4 h-4" strokeWidth={2} />
      {label ?? defaultLabel}
    </span>
  );
}
