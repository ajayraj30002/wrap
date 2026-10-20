import { useState, type FormEvent } from "react";
import { useAuth } from "../contexts/AuthContext";
import { useToast } from "../contexts/ToastContext";
import { useTheme } from "../contexts/ThemeContext";
import { apiClient } from "../lib/apiClient";
import { KeyRound, ArrowRight, Sun, Moon } from "lucide-react";

export function Setup() {
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const { completeSetup, login } = useAuth();
  const { toast } = useToast();
  const { theme, toggleTheme } = useTheme();

  const handleSetup = async (e: FormEvent) => {
    e.preventDefault();
    if (password !== confirmPassword) {
      toast({ title: "Validation Error", description: "Passwords do not match", type: "error" });     
      return;
    }
    if (password.length < 8) {
      toast({ title: "Validation Error", description: "Password must be at least 8 characters", type: "error" });           
      return;
    }

    setLoading(true);
    try { 
      await apiClient.post("/api/auth/setup", { password });
      await apiClient.post("/api/auth/login", { password });
      toast({ title: "Setup Complete", description: "Admin account created successfully.", type: "success" });
      completeSetup();
      login();
    } catch (err: any) {
      toast({ title: "Setup Failed", description: err.data?.detail || err.message || "An error occurred", type: "error" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-container">
      {/* Top right theme toggle */}
      <div style={{ position: "fixed", top: "1.25rem", right: "1.25rem" }}>
        <button
          className="btn btn-ghost"
          onClick={toggleTheme}
          title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          style={{ padding: "0.4rem" }}
        >
          {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
        </button>
      </div>

      <div className="auth-card">
        {/* Brand Header */}
        <div style={{ display: "flex", justifyContent: "center", marginBottom: "1.25rem" }}>
          <img
            src={theme === "light" ? "/brand-logo-light.png" : "/brand-logo.png"}
            alt="WRAP Console"
            style={{
              height: "36px",
              width: "auto",
              display: "block",
            }}
          />
        </div>

        <div className="auth-header">
          <h1 className="auth-title">Initialize WRAP</h1>
          <p className="auth-desc">Create your local admin password to secure your gateway.</p>
        </div>

        <form onSubmit={handleSetup} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div className="form-group">
            <label className="form-label" htmlFor="setup-password">Admin Password</label>
            <input
              id="setup-password"
              type="password"
              className="form-input"
              placeholder="Minimum 8 characters"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              autoFocus
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="setup-confirm-password">Confirm Password</label>
            <input
              id="setup-confirm-password"
              type="password"
              className="form-input"
              placeholder="Re-enter password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              disabled={loading}
            />
          </div>

          <button
            type="submit"
            className="btn btn-primary w-full"
            disabled={loading}
            style={{ height: "36px", marginTop: "0.25rem", gap: "0.5rem" }}
          >
            {loading ? (
              <span>Initializing...</span>
            ) : (
              <>
                <KeyRound size={14} />
                <span>Initialize Gateway</span>
                <ArrowRight size={14} />
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
