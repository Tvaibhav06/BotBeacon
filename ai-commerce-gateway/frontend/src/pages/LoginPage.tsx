import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { ShoppingBag } from "lucide-react";
import { Button } from "../design-system/Button";
import { Card } from "../design-system/Card";
import { api } from "../lib/api";
import { useAuth } from "../lib/AuthContext";

export function LoginPage() {
  const [email, setEmail] = useState("admin@velocitysports.demo");
  const [password, setPassword] = useState("demo1234");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { login } = useAuth();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const { access_token } = await api.login(email, password);
      // Decode merchant ID from JWT payload
      const payload = JSON.parse(atob(access_token.split(".")[1]));
      login(access_token, payload.sub, "Velocity Sports");
      navigate("/passport");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="flex items-center gap-2 justify-center mb-8">
          <div className="w-8 h-8 bg-ink rounded-md flex items-center justify-center">
            <ShoppingBag className="w-5 h-5 text-lime" strokeWidth={2} />
          </div>
          <span className="font-heading font-bold text-ink text-lg">AI Commerce Gateway</span>
        </div>

        <Card>
          <h1 className="font-heading text-xl font-semibold text-ink mb-6">Sign in</h1>
          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block font-body text-sm text-ink/60 mb-1">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full border border-border rounded-lg px-3 py-2 font-body text-sm text-ink bg-white focus:outline-none focus:ring-2 focus:ring-ink/20"
                required
              />
            </div>
            <div>
              <label className="block font-body text-sm text-ink/60 mb-1">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full border border-border rounded-lg px-3 py-2 font-body text-sm text-ink bg-white focus:outline-none focus:ring-2 focus:ring-ink/20"
                required
              />
            </div>
            {error && (
              <p className="font-body text-sm text-coral">{error}</p>
            )}
            <Button type="submit" variant="primary" className="w-full" loading={loading}>
              Sign in
            </Button>
          </form>
          <p className="font-body text-xs text-ink/40 mt-4 text-center">
            No account?{" "}
            <Link to="/onboarding" className="text-ink underline">
              Onboard merchant
            </Link>
          </p>
        </Card>

        <p className="font-body text-xs text-ink/30 text-center mt-4">
          Demo: admin@velocitysports.demo / demo1234
        </p>
      </div>
    </div>
  );
}
