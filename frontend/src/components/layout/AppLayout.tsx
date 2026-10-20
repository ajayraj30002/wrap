import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { Outlet } from "react-router-dom";

export function AppLayout() {
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-viewport">
        <Topbar />
        <main className="content-scrollable">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
