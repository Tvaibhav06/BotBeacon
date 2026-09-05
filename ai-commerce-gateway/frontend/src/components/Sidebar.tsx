import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import {
  FileText, ShoppingBag, Settings, Zap, Receipt, BookOpen, LogOut
} from "lucide-react";
import { useAuth } from "../lib/AuthContext";

const NAV_ITEMS = [
  { to: "/passport",   label: "Passport & Catalog", icon: FileText },
  { to: "/rules",      label: "Rules",               icon: Settings },
  { to: "/simulator",  label: "Buyer Simulator",     icon: Zap },
  { to: "/transactions", label: "Transactions",      icon: Receipt },
  { to: "/audit",      label: "Audit Log",           icon: BookOpen },
];

export function Sidebar() {
  const { merchantName, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <aside className="w-60 min-h-screen bg-ink flex flex-col">
      {/* Brand */}
      <div className="px-6 py-5 border-b border-white/10">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 bg-lime rounded-md flex items-center justify-center">
            <ShoppingBag className="w-4 h-4 text-ink" strokeWidth={2} />
          </div>
          <div>
            <p className="font-heading font-semibold text-white text-sm leading-tight">
              AI Commerce Gateway
            </p>
            <p className="font-body text-white/40 text-xs">{merchantName ?? "Merchant"}</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              [
                "flex items-center gap-3 px-3 py-2 rounded-md font-body text-sm transition-colors",
                isActive
                  ? "bg-lime text-ink font-medium"
                  : "text-white/60 hover:text-white hover:bg-white/10",
              ].join(" ")
            }
          >
            <Icon className="w-4 h-4 flex-shrink-0" strokeWidth={1.75} />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Logout */}
      <div className="px-3 py-4 border-t border-white/10">
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-3 px-3 py-2 rounded-md font-body text-sm text-white/50 hover:text-white hover:bg-white/10 transition-colors"
        >
          <LogOut className="w-4 h-4" strokeWidth={1.75} />
          Sign out
        </button>
      </div>
    </aside>
  );
}
