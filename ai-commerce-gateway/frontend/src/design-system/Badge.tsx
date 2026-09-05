import React from "react";

type BadgeVariant = "lime" | "coral" | "surface" | "ink";

interface BadgeProps {
  variant?: BadgeVariant;
  className?: string;
  children: React.ReactNode;
}

const variantClasses: Record<BadgeVariant, string> = {
  lime: "bg-lime text-ink",
  coral: "bg-coral text-white",
  surface: "bg-surface text-ink border border-border",
  ink: "bg-ink text-white",
};

export function Badge({ variant = "surface", className = "", children }: BadgeProps) {
  return (
    <span
      className={[
        "inline-flex items-center px-3 py-0.5 rounded-pill text-xs font-body font-medium",
        variantClasses[variant],
        className,
      ].join(" ")}
    >
      {children}
    </span>
  );
}
