import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./lib/AuthContext";
import { DashboardLayout } from "./components/DashboardLayout";
import { ComponentShowcase } from "./pages/DevComponents";
import { LoginPage } from "./pages/LoginPage";
import { OnboardingWizard } from "./pages/OnboardingWizard";
import { PassportPage } from "./pages/PassportPage";
import { RulesPage, SimulatorPage, TransactionsPage } from "./pages/StubPages";
import { AuditLogPage } from "./pages/AuditLogPage";
import { TransactionAuditPage } from "./pages/TransactionAuditPage";

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="/onboarding" element={<OnboardingWizard />} />

          {/* Phase 0 showcase */}
          <Route path="/dev/components" element={<ComponentShowcase />} />

          {/* Protected dashboard */}
          <Route element={<DashboardLayout />}>
            <Route path="/passport"     element={<PassportPage />} />
            <Route path="/rules"        element={<RulesPage />} />
            <Route path="/simulator"    element={<SimulatorPage />} />
            <Route path="/transactions" element={<TransactionsPage />} />
            <Route path="/transactions/:id/audit" element={<TransactionAuditPage />} />
            <Route path="/audit"        element={<AuditLogPage />} />
          </Route>

          {/* Root redirect */}
          <Route path="/" element={<Navigate to="/login" replace />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
