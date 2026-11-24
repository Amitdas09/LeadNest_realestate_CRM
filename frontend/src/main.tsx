import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { Loading, ToastProvider } from "./components/ui";
import "./index.css";
import { AuthProvider, isManager, useAuth } from "./lib/auth";
import Conversations from "./pages/Conversations";
import Dashboard from "./pages/Dashboard";
import FollowUps from "./pages/FollowUps";
import Forms from "./pages/Forms";
import Imports from "./pages/Imports";
import LeadDetail from "./pages/LeadDetail";
import Leads from "./pages/Leads";
import Login from "./pages/Login";
import Properties from "./pages/Properties";
import SettingsPage from "./pages/Settings";

const qc = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: true, staleTime: 3000 } } });

function Protected({ children, manager }: { children: React.ReactNode; manager?: boolean }) {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" replace />;
  if (manager && !isManager(user)) return <Navigate to="/" replace />;
  return <>{children}</>;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <AuthProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route element={<Protected><Layout /></Protected>}>
                <Route index element={<Dashboard />} />
                <Route path="leads" element={<Leads />} />
                <Route path="leads/:id" element={<LeadDetail />} />
                <Route path="conversations" element={<Conversations />} />
                <Route path="conversations/:convId" element={<Conversations />} />
                <Route path="followups" element={<FollowUps />} />
                <Route path="properties" element={<Protected manager><Properties /></Protected>} />
                <Route path="forms" element={<Protected manager><Forms /></Protected>} />
                <Route path="imports" element={<Protected manager><Imports /></Protected>} />
                <Route path="settings" element={<Protected manager><SettingsPage /></Protected>} />
              </Route>
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </ToastProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
