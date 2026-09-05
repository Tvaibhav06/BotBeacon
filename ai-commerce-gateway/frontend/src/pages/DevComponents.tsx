import React from "react";
import { Button } from "../design-system/Button";
import { Card } from "../design-system/Card";
import { Badge } from "../design-system/Badge";
import { StatusPill } from "../design-system/StatusPill";
import { ShoppingBag, Shield, Zap, Check, X } from "lucide-react";

export function ComponentShowcase() {
  return (
    <div className="min-h-screen bg-surface p-8">
      <div className="max-w-4xl mx-auto space-y-10">

        {/* Header */}
        <div>
          <h1 className="font-heading text-3xl font-bold text-ink">
            Design System — Component Showcase
          </h1>
          <p className="font-body text-sm text-ink/60 mt-1">
            Visual QA for Phase 0. All components must use <code className="bg-surface px-1 rounded text-xs">--ink</code> /
            <code className="bg-lime/40 px-1 rounded text-xs ml-1">--lime</code> palette — no default Tailwind indigo.
          </p>
        </div>

        {/* Color Palette */}
        <section>
          <h2 className="font-heading text-xl font-semibold text-ink mb-4">Color Tokens</h2>
          <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
            {[
              { name: "--ink", bg: "bg-ink", text: "text-white", hex: "#191A23" },
              { name: "--lime", bg: "bg-lime", text: "text-ink", hex: "#B9FF66" },
              { name: "--white", bg: "bg-white border border-border", text: "text-ink", hex: "#FFFFFF" },
              { name: "--surface", bg: "bg-surface border border-border", text: "text-ink", hex: "#F3F3F3" },
              { name: "--border", bg: "bg-border", text: "text-ink", hex: "#DADADB" },
              { name: "--coral", bg: "bg-coral", text: "text-white", hex: "#FF6B57" },
            ].map((color) => (
              <div key={color.name} className="space-y-1">
                <div className={`${color.bg} ${color.text} rounded-card h-16 flex items-end p-2`}>
                  <span className="text-xs font-body font-medium">{color.name}</span>
                </div>
                <p className="text-xs font-body text-ink/50">{color.hex}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Typography */}
        <section>
          <h2 className="font-heading text-xl font-semibold text-ink mb-4">Typography</h2>
          <Card>
            <div className="space-y-3">
              <p className="font-heading text-3xl font-bold text-ink">Space Grotesk — Heading</p>
              <p className="font-heading text-xl font-semibold text-ink">Space Grotesk — Subheading</p>
              <p className="font-body text-base text-ink">Inter — Body copy, table data, form labels</p>
              <p className="font-body text-sm text-ink/60">Inter — Secondary / muted text</p>
              <p className="font-heading text-5xl font-bold text-ink">₹5,998</p>
              <p className="font-body text-xs text-ink/40">Caption / label</p>
            </div>
          </Card>
        </section>

        {/* Buttons */}
        <section>
          <h2 className="font-heading text-xl font-semibold text-ink mb-4">Buttons</h2>
          <Card>
            <div className="flex flex-wrap gap-3 items-center">
              <Button variant="primary">Primary</Button>
              <Button variant="lime">Lime</Button>
              <Button variant="outline">Outline</Button>
              <Button variant="ghost">Ghost</Button>
              <Button variant="primary" loading>Loading</Button>
              <Button variant="primary" disabled>Disabled</Button>
            </div>
            <div className="flex flex-wrap gap-3 items-center mt-4">
              <Button variant="primary" size="sm">Small</Button>
              <Button variant="primary" size="md">Medium</Button>
              <Button variant="primary" size="lg">Large</Button>
            </div>
          </Card>
        </section>

        {/* Cards */}
        <section>
          <h2 className="font-heading text-xl font-semibold text-ink mb-4">Cards</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Card variant="default">
              <p className="font-body text-sm text-ink/60 mb-1">Default</p>
              <p className="font-heading font-semibold text-ink">White background</p>
            </Card>
            <Card variant="surface">
              <p className="font-body text-sm text-ink/60 mb-1">Surface</p>
              <p className="font-heading font-semibold text-ink">F3F3F3 background</p>
            </Card>
            <Card variant="ink">
              <p className="font-body text-sm text-white/60 mb-1">Ink</p>
              <p className="font-heading font-semibold text-white">Dark card</p>
            </Card>
          </div>
        </section>

        {/* Badges */}
        <section>
          <h2 className="font-heading text-xl font-semibold text-ink mb-4">Badges</h2>
          <Card>
            <div className="flex flex-wrap gap-3 items-center">
              <Badge variant="lime">Approved</Badge>
              <Badge variant="coral">Blocked</Badge>
              <Badge variant="surface">Pending</Badge>
              <Badge variant="ink">Active</Badge>
            </div>
          </Card>
        </section>

        {/* Status Pills */}
        <section>
          <h2 className="font-heading text-xl font-semibold text-ink mb-4">Status Pills</h2>
          <Card>
            <div className="flex flex-wrap gap-6 items-center">
              <StatusPill status="approved" />
              <StatusPill status="blocked" />
              <StatusPill status="pending" />
              <StatusPill status="warning" />
              <StatusPill status="approved" label="Within buyer limit" />
              <StatusPill status="blocked" label="Razorpay was never called" />
            </div>
          </Card>
        </section>

        {/* Decision Receipt Preview */}
        <section>
          <h2 className="font-heading text-xl font-semibold text-ink mb-4">Decision Receipt Preview</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">

            {/* Approved */}
            <Card variant="ink">
              <p className="font-body text-xs text-white/40 tracking-widest mb-4">
                AI COMMERCE DECISION RECEIPT
              </p>
              <div className="space-y-3 text-sm font-body">
                <div>
                  <p className="text-white/40 text-xs tracking-wider">CUSTOMER REQUEST</p>
                  <p className="text-white mt-0.5">Find me running shoes under ₹6,000</p>
                </div>
                <div className="flex justify-between">
                  <span className="text-white/40">Considered</span>
                  <span className="text-white font-medium">18 products</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-white/40">Selected</span>
                  <span className="text-white font-medium">Velocity Pro — ₹5,499</span>
                </div>
                <div>
                  <p className="text-white/40 text-xs tracking-wider mb-1">WHY</p>
                  {["Best fit for intent", "In stock", "Within budget"].map((r) => (
                    <div key={r} className="flex items-center gap-2">
                      <Check className="w-4 h-4 text-lime" strokeWidth={2.5} />
                      <span className="text-white/80">{r}</span>
                    </div>
                  ))}
                </div>
                <div className="border-t border-white/10 pt-3">
                  <div className="flex justify-between items-baseline">
                    <span className="text-white/40 text-xs tracking-wider">FINAL</span>
                    <span className="font-heading font-bold text-3xl text-white">₹5,998</span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Check className="w-4 h-4 text-lime" />
                  <span className="text-white/80 text-xs">Within buyer limit</span>
                </div>
                <div className="flex items-center gap-2">
                  <Check className="w-4 h-4 text-lime" />
                  <span className="text-white/80 text-xs">Razorpay verified</span>
                </div>
              </div>
            </Card>

            {/* Blocked */}
            <Card variant="ink">
              <p className="font-body text-xs text-white/40 tracking-widest mb-4">
                AI COMMERCE DECISION RECEIPT
              </p>
              <div className="space-y-3 text-sm font-body">
                <div>
                  <p className="text-white/40 text-xs tracking-wider">CUSTOMER REQUEST</p>
                  <p className="text-white mt-0.5">Buy the ₹8,999 version instead</p>
                </div>
                <div className="mt-4 p-3 border border-coral/30 rounded-card bg-coral/10">
                  <div className="flex items-center gap-2 mb-2">
                    <X className="w-5 h-5 text-coral" strokeWidth={2.5} />
                    <span className="font-heading font-semibold text-coral text-lg">BLOCKED</span>
                  </div>
                  <div className="space-y-1 text-xs">
                    <div className="flex justify-between">
                      <span className="text-white/40">Buyer limit</span>
                      <span className="text-white">₹6,000</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-white/40">Requested</span>
                      <span className="text-coral font-medium">₹8,999</span>
                    </div>
                  </div>
                </div>
                <p className="text-white/50 text-xs mt-4">Razorpay was never called.</p>
              </div>
            </Card>

          </div>
        </section>

        {/* Icons check */}
        <section>
          <h2 className="font-heading text-xl font-semibold text-ink mb-4">Icons (lucide-react)</h2>
          <Card>
            <div className="flex gap-4 text-ink">
              <ShoppingBag className="w-5 h-5" strokeWidth={1.5} />
              <Shield className="w-5 h-5" strokeWidth={1.5} />
              <Zap className="w-5 h-5" strokeWidth={1.5} />
              <Check className="w-5 h-5" strokeWidth={2} />
              <X className="w-5 h-5" strokeWidth={2} />
            </div>
            <p className="font-body text-xs text-ink/40 mt-2">
              Consistent stroke weight — no filled/glossy icons.
            </p>
          </Card>
        </section>

      </div>
    </div>
  );
}
