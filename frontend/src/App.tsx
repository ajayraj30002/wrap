import type { ReactNode } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AppLayout } from "./components/layout/AppLayout";
import { useAuth, AuthProvider } from "./contexts/AuthContext";
import { ToastProvider } from "./contexts/ToastContext";
import { ThemeProvider } from "./contexts/ThemeContext";

// Pages
import { Login } from "./pages/Login";
import { Setup } from "./pages/Setup";
import { Overview } from "./pages/Overview";
import { Requests } from "./pages/Requests";
import { Workers } from "./pages/Workers";
import { Quota } from "./pages/Quota";
import { Analytics } from "./pages/Analytics";
import { Settings } from "./pages/Settings";
import { LiveStream } from "./pages/LiveStream";
import { LiveDockProvider } from "./contexts/LiveDockContext";

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, needsSetup, isLoading } = useAuth();
  if (isLoading) return <div style={{ display: "flex", height: "100vh", alignItems: "center", justifyContent: "center", fontFamily: "var(--font-mono)", color: "var(--text-secondary)" }}>Loading WRAP Console...</div>;
  if (needsSetup) return <Navigate to="/setup" replace />;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function AppContent() {
  const { isAuthenticated, needsSetup } = useAuth();
  return (
    <Routes>
      <Route path="/setup" element={needsSetup ? <Setup /> : <Navigate to="/" replace />} />
      <Route path="/login" element={needsSetup ? <Navigate to="/setup" replace /> : isAuthenticated ? <Navigate to="/" replace /> : <Login />} />
      <Route path="/" element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<Overview />} />
        <Route path="live" element={<LiveStream />} />
        <Route path="requests" element={<Requests />} />
        <Route path="workers" element={<Workers />} />
        <Route path="quota" element={<Quota />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="settings" element={<Navigate to="/settings/api-keys" replace />} />
        <Route path="settings/:tab" element={<Settings />} />
        {/* Backward compatible redirects */}
        <Route path="budgets" element={<Navigate to="/settings/budgets" replace />} />
        <Route path="finance" element={<Navigate to="/settings/budgets" replace />} />
        <Route path="credentials" element={<Navigate to="/settings/providers" replace />} />
        <Route path="api-access" element={<Navigate to="/settings/setup" replace />} />
        <Route path="workflows" element={<Navigate to="/settings/setup" replace />} />
        <Route path="setup-guide" element={<Navigate to="/settings/setup" replace />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <ToastProvider>
        <AuthProvider>
          <LiveDockProvider>
            <BrowserRouter>
              <AppContent />
            </BrowserRouter>
          </LiveDockProvider>
        </AuthProvider>
      </ToastProvider>
    </ThemeProvider>
  );
}
