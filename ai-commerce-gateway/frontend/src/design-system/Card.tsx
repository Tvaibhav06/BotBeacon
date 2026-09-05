import React from "react";

type CardVariant = "default" | "surface" | "ink";

interface CardProps {
  variant?: CardVariant;
  className?: string;
  children: React.ReactNode;
}

const variantClasses: Record<CardVariant, string> = {
  default: "bg-white border border-border",
  surface: "bg-surface border border-border",
  ink: "bg-ink text-white border-transparent",
};

export function Card({ variant = "default", className = "", children }: CardProps) {
  return (
    <div
      className={[
        "rounded-card p-6",
        variantClasses[variant],
        className,
      ].join(" ")}
    >
      {children}
    </div>
  );
}
