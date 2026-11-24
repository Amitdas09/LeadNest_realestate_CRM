import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { api, auth } from "./api";

export type Me = { id: string; email: string; full_name: string; role: "admin" | "manager" | "agent" };

type Ctx = { user: Me | null; loading: boolean; login: (email: string, password: string) => Promise<void>; logout: () => void };
const AuthCtx = createContext<Ctx>(null as any);
export const useAuth = () => useContext(AuthCtx);
export const isManager = (u: Me | null) => !!u && (u.role === "admin" || u.role === "manager");

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!auth.get()) { setLoading(false); return; }
    api<Me>("/api/v1/auth/me").then(setUser).catch(() => auth.clear()).finally(() => setLoading(false));
  }, []);

  const login = async (email: string, password: string) => {
    const r = await api<{ access_token: string; user: Me }>("/api/v1/auth/login", { body: { email, password } });
    auth.set(r.access_token);
    setUser(r.user);
  };
  const logout = () => { auth.clear(); setUser(null); window.location.href = "/login"; };

  return <AuthCtx.Provider value={{ user, loading, login, logout }}>{children}</AuthCtx.Provider>;
}
