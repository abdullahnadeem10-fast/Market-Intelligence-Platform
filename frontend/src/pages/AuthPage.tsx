import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { BarChart3, Bot, Radar, ShieldCheck } from "lucide-react";
import { Alert, Button, Field, inputClass } from "../components/ui";
import { useAuth } from "../lib/auth";

export default function AuthPage({ mode }: { mode: "login" | "register" }) {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const isLogin = mode === "login";

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!isLogin && (password.length < 8 || !/\d/.test(password) || !/[a-z]/i.test(password))) {
      setError("Password must be at least 8 characters and include a letter and a number.");
      return;
    }
    setBusy(true);
    try {
      if (isLogin) await login(email, password);
      else await register(email, password, fullName);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from && from !== "/login" ? from : "/", { replace: true });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="hidden flex-col justify-between bg-slate-900 p-12 text-white lg:flex">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-600">
            <Bot className="h-5 w-5" />
          </div>
          <span className="font-semibold">Market Intelligence</span>
        </div>
        <div className="max-w-md">
          <h1 className="text-3xl font-semibold leading-tight tracking-tight">
            Track companies and see what changes in your market, with sources for every claim.
          </h1>
          <ul className="mt-8 space-y-4 text-sm text-slate-300">
            <li className="flex gap-3"><Radar className="h-5 w-5 shrink-0 text-indigo-400" /> Collects news automatically from public APIs on a schedule</li>
            <li className="flex gap-3"><BarChart3 className="h-5 w-5 shrink-0 text-indigo-400" /> Activity, category and trend analytics across your tracked companies</li>
            <li className="flex gap-3"><ShieldCheck className="h-5 w-5 shrink-0 text-indigo-400" /> AI summaries limited to collected sources, each insight cited</li>
          </ul>
        </div>
        <p className="text-xs text-slate-500">Portfolio project · FastAPI · PostgreSQL · React</p>
      </div>

      <div className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <h2 className="text-2xl font-semibold tracking-tight">{isLogin ? "Welcome back" : "Create your account"}</h2>
          <p className="mt-1 text-sm text-slate-500">
            {isLogin ? "Sign in to your workspace." : "Start tracking your market in minutes."}
          </p>
          <form onSubmit={submit} className="mt-8 space-y-4">
            {error && <Alert>{error}</Alert>}
            {!isLogin && (
              <Field label="Full name">
                <input className={inputClass} value={fullName} onChange={(e) => setFullName(e.target.value)} maxLength={120} autoComplete="name" />
              </Field>
            )}
            <Field label="Email">
              <input className={inputClass} type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
            </Field>
            <Field label="Password" hint={isLogin ? undefined : "At least 8 characters, with a letter and a number."}>
              <input
                className={inputClass}
                type="password"
                required
                maxLength={64}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete={isLogin ? "current-password" : "new-password"}
              />
            </Field>
            <Button type="submit" loading={busy} className="w-full">
              {isLogin ? "Sign in" : "Create account"}
            </Button>
          </form>
          <p className="mt-6 text-center text-sm text-slate-500">
            {isLogin ? "No account yet? " : "Already have an account? "}
            <Link to={isLogin ? "/register" : "/login"} className="font-medium text-indigo-600 hover:text-indigo-500">
              {isLogin ? "Create one" : "Sign in"}
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
