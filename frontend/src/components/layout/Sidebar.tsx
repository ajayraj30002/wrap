import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Layers,
  Server,
  Activity,
  Database,
  Key,
  Shield,
  Sliders,
  Cpu,
  DollarSign,
  Terminal,
  Zap,
} from "lucide-react";
import { useTheme } from "../../contexts/ThemeContext";

export function Sidebar() {
  const { theme } = useTheme();
  const logoSrc = theme === "light" ? "/brand-logo-light.png" : "/brand-logo.png";

  const primaryNav = [
    { to: "/dashboard", icon: <LayoutDashboard size={15} />, label: "Overview" },
    { to: "/requests", icon: <Layers size={15} />, label: "Requests" },
    { to: "/workers", icon: <Server size={15} />, label: "Workers" },
    { to: "/quota", icon: <Database size={15} />, label: "Quota" },
    { to: "/analytics", icon: <Activity size={15} />, label: "Analytics" },
  ];

  const secondaryNav = [
    { to: "/settings/api-keys", icon: <Key size={14} />, label: "Gateway Keys" },
    { to: "/settings/budgets", icon: <DollarSign size={14} />, label: "Budgets & Spend" },
    { to: "/settings/model-groups", icon: <Layers size={14} />, label: "Virtual Tiers" },
    { to: "/settings/providers", icon: <Cpu size={14} />, label: "Provider Keys" },
    { to: "/settings/policies", icon: <Sliders size={14} />, label: "Policies" },
    { to: "/settings/setup", icon: <Terminal size={14} />, label: "Workflow Setup" },
    { to: "/settings/system", icon: <Shield size={14} />, label: "System" },
  ];

  return (
    <aside className="enterprise-sidebar">
      {/* Brand Header */}
      <div className="sidebar-brand-container">
        <NavLink to="/dashboard" className="sidebar-brand-link">
          <img
            src={logoSrc}
            alt="WRAP"
            className="sidebar-brand-logo"
          />
        </NavLink>
      </div>

      {/* Nav List */}
      <div className="sidebar-nav-container">
        {/* Primary Operational Section */}
        <nav className="sidebar-nav-group">
          <div className="sidebar-group-title">
            Operations
          </div>
          {primaryNav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `sidebar-nav-item ${isActive ? "active" : ""}`}
            >
              <span className="sidebar-item-icon">{item.icon}</span>
              <span className="sidebar-item-label">{item.label}</span>
            </NavLink>
          ))}
        </nav>

        {/* Secondary Settings Layer */}
        <nav className="sidebar-nav-group">
          <div className="sidebar-group-title">
            Infrastructure & Control
          </div>
          {secondaryNav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `sidebar-nav-item secondary ${isActive ? "active" : ""}`}
            >
              <span className="sidebar-item-icon">{item.icon}</span>
              <span className="sidebar-item-label">{item.label}</span>
            </NavLink>
          ))}
        </nav>
      </div>

      {/* Sidebar Footer: Gateway Engine Pulse */}
      <div className="sidebar-footer">
        <div className="sidebar-footer-card">
          <div className="sidebar-footer-header">
            <span className="sidebar-engine-icon">
              <Zap size={12} />
            </span>
            <div className="sidebar-engine-text">
              <span className="sidebar-engine-title">Self-Healing Gateway</span>
              <span className="sidebar-engine-status">Zero-overhead runtime</span>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}

