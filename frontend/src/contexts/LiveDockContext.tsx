import { createContext, useContext, useState, type ReactNode } from "react";

export type DockPosition = "closed" | "right" | "bottom" | "minimized";

interface LiveDockContextType {
  dockPosition: DockPosition;
  setDockPosition: (pos: DockPosition) => void;
  openRight: () => void;
  openBottom: () => void;
  closeDock: () => void;
  toggleDock: (preferredPos?: "right" | "bottom") => void;
}

const LiveDockContext = createContext<LiveDockContextType | null>(null);

export function LiveDockProvider({ children }: { children: ReactNode }) {
  const [dockPosition, setDockPositionState] = useState<DockPosition>(() => {
    try {
      const saved = localStorage.getItem("wrap_live_dock_pos");
      if (saved === "right" || saved === "bottom" || saved === "minimized") return saved;
    } catch {
      // Fallback
    }
    return "closed";
  });

  const setDockPosition = (pos: DockPosition) => {
    setDockPositionState(pos);
    try {
      if (pos !== "closed") {
        localStorage.setItem("wrap_live_dock_pos", pos);
      }
    } catch {
      // Ignore
    }
  };

  const openRight = () => setDockPosition("right");
  const openBottom = () => setDockPosition("bottom");
  const closeDock = () => setDockPosition("closed");

  const toggleDock = (preferredPos: "right" | "bottom" = "right") => {
    if (dockPosition === "closed") {
      setDockPosition(preferredPos);
    } else {
      setDockPosition("closed");
    }
  };

  return (
    <LiveDockContext.Provider
      value={{
        dockPosition,
        setDockPosition,
        openRight,
        openBottom,
        closeDock,
        toggleDock,
      }}
    >
      {children}
    </LiveDockContext.Provider>
  );
}

export function useLiveDock() {
  const ctx = useContext(LiveDockContext);
  if (!ctx) {
    throw new Error("useLiveDock must be used within a LiveDockProvider");
  }
  return ctx;
}
