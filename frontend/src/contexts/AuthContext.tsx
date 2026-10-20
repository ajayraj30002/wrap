import React, { createContext, useContext, useState, useEffect } from "react";
import { useToast } from "./ToastContext";

interface AuthContextType {
  isAuthenticated: boolean;
  needsSetup: boolean;
  isLoading: boolean;
  login: () => void;
  logout: () => void;
  completeSetup: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

import { apiClient } from "../lib/apiClient";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [needsSetup, setNeedsSetup] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const { toast } = useToast();

  useEffect(() => {
    const checkAuthStatus = async () => {
      try {
        // First try to check if we have a valid session
        try {
          await apiClient.get('/api/auth/session');
          setIsAuthenticated(true);
        } catch (e: any) {
          if (e.status === 401) {
            // Unauthenticated. Check if we need setup
            const res = await apiClient.get('/api/auth/me');
            if (res.setup_required) {
              setNeedsSetup(true);
            }
          } else {
            throw e; // Rethrow to outer catch
          }
        }
      } catch (error) {
        toast({
          title: "Backend Connection Error",
          description: "Could not connect to the WRAP backend.",
          type: "error"
        });
        setIsAuthenticated(false);
      } finally {
        setIsLoading(false);
      }
    };

    // Listen for global unauthorized events
    const handleUnauthorized = () => {
      setIsAuthenticated(false);
    };
    window.addEventListener("unauthorized", handleUnauthorized);
    
    checkAuthStatus();
    
    return () => {
      window.removeEventListener("unauthorized", handleUnauthorized);
    };
  }, [toast]);

  const login = () => setIsAuthenticated(true);
  
  const logout = async () => {
    try {
      await apiClient.post('/api/auth/logout');
    } catch (e) {
      console.error(e);
    }
    setIsAuthenticated(false);
  };

  const completeSetup = () => {
    setNeedsSetup(false);
    setIsAuthenticated(true);
  };

  return (
    <AuthContext.Provider value={{ isAuthenticated, needsSetup, isLoading, login, logout, completeSetup }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
};
