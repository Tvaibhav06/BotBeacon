import React, { createContext, useContext, useState, useEffect } from "react";

interface AuthState {
  token: string | null;
  merchantId: string | null;
  merchantName: string | null;
}

interface AuthContextType extends AuthState {
  login: (token: string, merchantId: string, merchantName: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [auth, setAuth] = useState<AuthState>(() => {
    const stored = localStorage.getItem("acg_auth");
    return stored ? JSON.parse(stored) : { token: null, merchantId: null, merchantName: null };
  });

  const login = (token: string, merchantId: string, merchantName: string) => {
    const next = { token, merchantId, merchantName };
    setAuth(next);
    localStorage.setItem("acg_auth", JSON.stringify(next));
  };

  const logout = () => {
    setAuth({ token: null, merchantId: null, merchantName: null });
    localStorage.removeItem("acg_auth");
  };

  return (
    <AuthContext.Provider value={{ ...auth, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
