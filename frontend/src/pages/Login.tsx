import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { useToast } from "../contexts/ToastContext";
import { useTheme } from "../contexts/ThemeContext";
import { apiClient } from "../lib/apiClient";
import { LiveDAGPipeline } from "../components/ui/LiveDAGPipeline";
import {
  KeyRound,
  ArrowRight,
  Sun,
  Moon,
  Eye,
  EyeOff,
  BookOpen,
  ExternalLink,
  Lock,
  Flame,
  Zap,
  ShieldCheck,
  Server,
  Sparkles,
} from "lucide-react";

export function Login() {
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const { toast } = useToast();
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();

  const handleLogin = async (e: FormEvent) => {
    e.preventDefault();
    if (!password) return;
    setLoading(true);
    try {
      await apiClient.post("/api/auth/login", { password });
      login();
      navigate("/");
    } catch (err: any) {
      toast({
        title: "Authentication Failed",
        description: err.data?.detail || err.message || "Invalid master key. Please check your credentials and try again.",
        type: "error",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-viewport">
      {/* Ambient background mesh light orbs */}
      <div className="login-ambient-orb orb-primary" />
      <div className="login-ambient-orb orb-secondary" />

      {/* Fixed Top-Right Page Actions */}
      <nav className="login-page-top-actions">
        <a
          href="/docs"
          target="_blank"
          rel="noreferrer"
          className="page-doc-btn font-mono"
          title="Open API Documentation (Swagger UI)"
        >
          <BookOpen size={13} />
          <span>API Docs</span>
          <ExternalLink size={11} />
        </a>
        <button
          type="button"
          className="page-theme-btn"
          onClick={toggleTheme}
          title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
        >
          {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
        </button>
      </nav>

      {/* =========================================================================
          LEFT PANE: Architecture Narrative & Live Multi-Agent Execution Canvas
          ========================================================================= */}
      <section className="login-left-pane">
        {/* Top Branding (Precision Aligned) */}
        <header className="login-brand-header">
          <div className="brand-group">
            <img
              src={theme === "light" ? "/brand-logo-light.png" : "/brand-logo.png"}
              alt="WRAP Gateway"
              className="brand-logo-img"
            />
            <div className="brand-divider" />
            <div className="brand-badge-cluster font-mono">
              <span className="brand-version">v1.4.2 · PRODUCTION ENGINE</span>
              <span className="brand-status-dot" />
              <span className="brand-airgap">SELF-HOSTED</span>
            </div>
          </div>
        </header>

        {/* Hero Narrative (High-Authority Typography) */}
        <div className="login-hero-block">
          <div className="hero-kicker font-mono">
            <Sparkles size={11} className="text-accent" />
            <span>SELF-HEALING AI ENGINE</span>
          </div>
          <h1 className="hero-title">
            Multi-Agent Parallel Execution & Key Arbitrage
          </h1>
          <p className="hero-description">
            Decomposes prompts across specialized LPUs and auto-heals failed requests with zero-cost virtual key multiplexing.
          </p>
        </div>

        {/* Live Execution Flow Diagram (Frameless Topology Canvas) */}
        <div className="login-dag-canvas-container">
          <LiveDAGPipeline />
        </div>

        {/* Technical Specification Strip (Seamless Unified Architecture Grid) */}
        <div className="login-architecture-strip">
          <div className="arch-strip-col">
            <div className="arch-col-header">
              <div className="arch-col-title-group">
                <Zap size={13} className="text-accent" />
                <span className="arch-col-title font-sans">Parallel DAG Engine</span>
              </div>
              <span className="arch-col-chip font-mono text-accent">PARALLEL SPEED</span>
            </div>
            <p className="arch-col-desc">
              Decomposes complex prompts into concurrent workstreams, compressing sequential model waterfalls into a single critical path.
            </p>
          </div>

          <div className="arch-strip-col highlight-beast">
            <div className="arch-col-header">
              <div className="arch-col-title-group">
                <Flame size={13} style={{ color: "#f59e0b" }} />
                <span className="arch-col-title font-sans">Free-Tier Beast Multiplexer</span>
              </div>
              <span className="arch-col-chip font-mono text-warning">100% ARBITRAGE</span>
            </div>
            <p className="arch-col-desc">
              Rotates paired free-tier credential buckets into seamless high-QPS virtual tiers with zero compute costs.
            </p>
          </div>

          <div className="arch-strip-col">
            <div className="arch-col-header">
              <div className="arch-col-title-group">
                <ShieldCheck size={13} style={{ color: "#a855f7" }} />
                <span className="arch-col-title font-sans">Runaway Circuit Breakers</span>
              </div>
              <span className="arch-col-chip font-mono" style={{ color: "#a855f7" }}>HARD ISOLATED</span>
            </div>
            <p className="arch-col-desc">
              Hardware-isolated recursion depth safeguards and token velocity limits eliminate runaway agent loop billing.
            </p>
          </div>
        </div>

        {/* Left Footer Attribution */}
        <footer className="login-left-footer font-mono">
          <span>Open Source Core · Apache 2.0 / MIT · Self-Hosted & Private VPC</span>
          <span className="footer-dot">·</span>
          <span>OpenAI Drop-In Compatible (/v1/chat/completions)</span>
        </footer>
      </section>

      {/* =========================================================================
          RIGHT PANE: Floating Operator Security Enclave
          ========================================================================= */}
      <aside className="login-right-pane">
        {/* Centered Operator Authentication Console */}
        <div className="operator-card-core">
          <div className="operator-brand-crest">
            <div className="crest-halo" />
            <img
              src="/wrap-app-icon.png"
              alt="WRAP Engine"
              className="crest-icon"
            />
          </div>

          <div className="operator-header">
            <div className="operator-subheading-wrap">
              <span className="operator-subheading font-mono">
                <span className="gateway-dot" />
                GATEWAY CONTROL ROOM
              </span>
            </div>
            <h2 className="operator-title">Operator Authentication</h2>
            <p className="operator-subtitle">
              Enter your master admin key to inspect live model telemetry, manage virtual tiers, and configure provider credentials.
            </p>
          </div>

          <form onSubmit={handleLogin} className="operator-form">
            <div className="operator-field-group">
              <label className="operator-label font-mono" htmlFor="admin-password">
                <Lock size={11} className="text-accent" />
                <span>MASTER ADMIN KEY</span>
              </label>

              <div className="operator-input-container">
                <KeyRound size={14} className="operator-input-icon text-tertiary" />
                <input
                  id="admin-password"
                  type={showPassword ? "text" : "password"}
                  className="operator-input font-mono"
                  placeholder="Enter master admin key"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={loading}
                  autoFocus
                />
                <button
                  type="button"
                  className="operator-eye-btn"
                  onClick={() => setShowPassword(!showPassword)}
                  tabIndex={-1}
                  title={showPassword ? "Hide password" : "Show password"}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              className="operator-submit-btn font-sans"
              disabled={loading}
            >
              {loading ? (
                <span>Authenticating Enclave...</span>
              ) : (
                <>
                  <span>Enter Control Room</span>
                  <ArrowRight size={14} className="operator-btn-arrow" />
                </>
              )}
            </button>
          </form>
        </div>

        {/* Security & Compliance Trust Footer */}
        <footer className="operator-trust-footer font-sans">
          <div className="trust-item">
            <ShieldCheck size={13} className="text-success" />
            <span>AES-256 GCM</span>
          </div>
          <span className="trust-sep">·</span>
          <div className="trust-item">
            <Lock size={12} className="text-accent" />
            <span>Zero Retention</span>
          </div>
          <span className="trust-sep">·</span>
          <div className="trust-item">
            <Server size={12} className="text-tertiary" />
            <span>TLS 1.3 Strict</span>
          </div>
        </footer>
      </aside>
    </div>
  );
}

