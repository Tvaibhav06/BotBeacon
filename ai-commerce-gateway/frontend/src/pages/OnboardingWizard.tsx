import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, Upload, Settings, ShieldCheck } from "lucide-react";
import { Button } from "../design-system/Button";
import { Card } from "../design-system/Card";
import { api } from "../lib/api";
import { useAuth } from "../lib/AuthContext";

const STEPS = [
  { n: 1, label: "Connect & Upload",   icon: Upload },
  { n: 2, label: "Review & Validate",  icon: Check },
  { n: 3, label: "Configure Rules",    icon: Settings },
  { n: 4, label: "Activate Passport",  icon: ShieldCheck },
];

export function OnboardingWizard() {
  const [step, setStep] = useState(1);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [token, setToken] = useState("");
  const [merchantId, setMerchantId] = useState("");

  const navigate = useNavigate();
  const { login } = useAuth();

  const handleStep1 = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await api.onboard(name, email, password);
      const { access_token } = await api.login(email, password);
      const payload = JSON.parse(atob(access_token.split(".")[1]));
      setToken(access_token);
      setMerchantId(payload.sub);
      login(access_token, payload.sub, name);
      setStep(2);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error");
    } finally {
      setLoading(false);
    }
  };

  const handleActivate = async () => {
    setError("");
    setLoading(true);
    try {
      await api.activatePassport(merchantId, token);
      navigate("/passport");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Activation failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface flex items-center justify-center p-6">
      <div className="w-full max-w-2xl">
        <h1 className="font-heading text-2xl font-bold text-ink mb-2">Merchant Onboarding</h1>
        <p className="font-body text-sm text-ink/50 mb-8">Get your Commerce Passport live in 4 steps</p>

        {/* Step indicator */}
        <div className="flex items-center gap-0 mb-8">
          {STEPS.map((s, i) => {
            const done = step > s.n;
            const active = step === s.n;
            return (
              <React.Fragment key={s.n}>
                <div className="flex items-center gap-2">
                  <div className={[
                    "w-8 h-8 rounded-full flex items-center justify-center font-heading font-bold text-sm flex-shrink-0",
                    done ? "bg-lime text-ink" : active ? "bg-ink text-white" : "bg-border text-ink/40"
                  ].join(" ")}>
                    {done ? <Check className="w-4 h-4" strokeWidth={2.5} /> : s.n}
                  </div>
                  <span className={[
                    "font-body text-xs hidden sm:block",
                    active ? "text-ink font-medium" : "text-ink/40"
                  ].join(" ")}>{s.label}</span>
                </div>
                {i < STEPS.length - 1 && (
                  <div className={["flex-1 h-px mx-3", done ? "bg-lime" : "bg-border"].join(" ")} />
                )}
              </React.Fragment>
            );
          })}
        </div>

        {/* Step 1 — Create account */}
        {step === 1 && (
          <Card>
            <h2 className="font-heading text-lg font-semibold text-ink mb-4">01 — Create merchant account</h2>
            <form onSubmit={handleStep1} className="space-y-4">
              <div>
                <label className="block font-body text-sm text-ink/60 mb-1">Store / Brand name</label>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full border border-border rounded-lg px-3 py-2 font-body text-sm focus:outline-none focus:ring-2 focus:ring-ink/20"
                  placeholder="e.g. Velocity Sports"
                  required
                />
              </div>
              <div>
                <label className="block font-body text-sm text-ink/60 mb-1">Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full border border-border rounded-lg px-3 py-2 font-body text-sm focus:outline-none focus:ring-2 focus:ring-ink/20"
                  required
                />
              </div>
              <div>
                <label className="block font-body text-sm text-ink/60 mb-1">Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full border border-border rounded-lg px-3 py-2 font-body text-sm focus:outline-none focus:ring-2 focus:ring-ink/20"
                  required
                />
              </div>
              {error && <p className="text-coral text-sm font-body">{error}</p>}
              <div className="flex justify-end">
                <Button type="submit" variant="lime" loading={loading}>Continue</Button>
              </div>
            </form>
          </Card>
        )}

        {/* Step 2 — Review catalog */}
        {step === 2 && (
          <Card>
            <h2 className="font-heading text-lg font-semibold text-ink mb-2">02 — Review &amp; Validate Catalog</h2>
            <p className="font-body text-sm text-ink/50 mb-4">
              Your catalog is ready for review. Upload a CSV or add products manually from the Catalog page,
              then return here to continue.
            </p>
            <div className="bg-lime/10 border border-lime/30 rounded-lg p-4 mb-4">
              <p className="font-body text-sm text-ink">
                Account created. Check the <strong>Passport &amp; Catalog</strong> page to review products
                and validation issues before activating.
              </p>
            </div>
            <div className="flex justify-between">
              <Button variant="outline" onClick={() => navigate("/passport")}>View Catalog</Button>
              <Button variant="lime" onClick={() => setStep(3)}>Configure Rules</Button>
            </div>
          </Card>
        )}

        {/* Step 3 — Rules */}
        {step === 3 && (
          <Card>
            <h2 className="font-heading text-lg font-semibold text-ink mb-2">03 — Configure Rules</h2>
            <p className="font-body text-sm text-ink/50 mb-4">
              Set your AI commerce rules. You can refine these later from the Rules page.
            </p>
            <div className="space-y-3 text-sm font-body text-ink/60">
              <p>→ Max AI discount percentage</p>
              <p>→ Upsell enabled / disabled</p>
              <p>→ Minimum margin percentage</p>
              <p>→ Autonomous approval threshold amount</p>
            </div>
            <div className="flex justify-between mt-6">
              <Button variant="outline" onClick={() => navigate("/rules")}>Configure now</Button>
              <Button variant="lime" onClick={() => setStep(4)}>Skip for now</Button>
            </div>
          </Card>
        )}

        {/* Step 4 — Activate */}
        {step === 4 && (
          <Card>
            <h2 className="font-heading text-lg font-semibold text-ink mb-2">04 — Activate Commerce Passport</h2>
            <p className="font-body text-sm text-ink/50 mb-6">
              Activation runs final validation. If there are no error-severity issues,
              your Passport goes <strong>ACTIVE</strong> and your catalog is AI-buyer-ready.
            </p>
            {error && <p className="text-coral text-sm font-body mb-4">{error}</p>}
            <div className="flex justify-between">
              <Button variant="outline" onClick={() => setStep(3)}>Back</Button>
              <Button variant="lime" loading={loading} onClick={handleActivate}>
                Activate Passport
              </Button>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
