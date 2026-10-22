import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { Outlet } from "react-router-dom";
import { LiveExecutionDock } from "../ui/LiveExecutionDock";
import { useLiveDock } from "../../contexts/LiveDockContext";

export function AppLayout() {
  const { dockPosition } = useLiveDock();

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-viewport">
        <Topbar />
        <div
          className={`viewport-workspace-container ${
            dockPosition === "right"
              ? "docked-right"
              : dockPosition === "bottom"
              ? "docked-bottom"
              : ""
          }`}
        >
          <main className="content-scrollable">
            <Outlet />
          </main>
          <LiveExecutionDock />
        </div>
      </div>
    </div>
  );
}

