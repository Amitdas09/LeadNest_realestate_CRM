import { FormEvent, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Button, ErrorBox, Field } from "../components/ui";
import { useAuth } from "../lib/auth";
import { BRAND, LogoMark, Wordmark } from "../lib/brand";

export default function Login() {
  const { user, login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<any>(null);
  if (user) return <Navigate to="/" replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try { await login(email, password); nav("/"); } catch (err) { setError(err); } finally { setBusy(false); }
  };

  return (
    <div className="flex min-h-full flex-col bg-canvas">
      <main className="flex flex-1 items-center justify-center px-4 py-12">
        <div className="w-full max-w-[380px]">
          <div className="mb-8 flex flex-col items-center text-center">
            <LogoMark size={44} />
            <Wordmark className="mt-4 text-[26px]" />
            <h1 className="mt-3 text-[15px] font-normal text-ink-3">Sign in to your account</h1>
          </div>
          <form onSubmit={submit} className="space-y-4 rounded-xl border border-line bg-white p-6 shadow-xs">
            <Field label="Email"><input className="input h-10" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} autoFocus /></Field>
            <Field label="Password"><input className="input h-10" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
            <ErrorBox error={error} />
            <Button type="submit" loading={busy} className="h-10 w-full">Sign in</Button>
          </form>
          <p className="mt-6 text-center text-xs text-ink-4">Need access? Ask your administrator to create an account.</p>
        </div>
      </main>
      <footer className="pb-6 text-center text-xs text-ink-4">© {new Date().getFullYear()} {BRAND.name}</footer>
    </div>
  );
}
