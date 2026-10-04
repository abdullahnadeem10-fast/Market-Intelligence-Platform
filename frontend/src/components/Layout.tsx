import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { Activity, Bot, Building2, Cpu, Database, LayoutDashboard, LogOut, Menu, Sparkles, X } from "lucide-react";
import { useAuth } from "../lib/auth";
import { cx } from "./ui";

const nav = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/companies", label: "Companies", icon: Building2 },
  { to: "/analysis", label: "Market Intelligence", icon: Sparkles },
  { to: "/data", label: "Collected Data", icon: Database },
  { to: "/automation", label: "Automation", icon: Activity },
  { to: "/usage", label: "AI Usage", icon: Cpu },
];

export function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-white">
        <Bot className="h-4.5 w-4.5" />
      </div>
      <div className="leading-tight">
        <p className="text-sm font-semibold text-white">Market Intelligence</p>
        <p className="text-[11px] text-slate-400">Insights platform</p>
      </div>
    </div>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);

  const sidebar = (
    <div className="flex h-full flex-col bg-slate-900 px-3 py-5">
      <div className="px-2">
        <Logo />
      </div>
      <nav className="mt-8 flex-1 space-y-1">
        {nav.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={() => setOpen(false)}
            className={({ isActive }) =>
              cx(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition",
                isActive ? "bg-slate-800 text-white" : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200",
              )
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-slate-800 px-2 pt-4">
        <p className="truncate text-sm font-medium text-slate-200">{user?.full_name || "Account"}</p>
        <p className="truncate text-xs text-slate-400">{user?.email}</p>
        <button onClick={logout} className="mt-3 flex items-center gap-2 text-xs font-medium text-slate-400 hover:text-white">
          <LogOut className="h-3.5 w-3.5" /> Sign out
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 hidden w-60 lg:block">{sidebar}</aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/50" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64">{sidebar}</aside>
        </div>
      )}
      <div className="lg:pl-60">
        <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-slate-200 bg-white/80 px-4 py-3 backdrop-blur lg:hidden">
          <button onClick={() => setOpen(!open)} className="rounded-md p-1.5 text-slate-600 hover:bg-slate-100" aria-label="Toggle menu">
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
          <span className="text-sm font-semibold">Market Intelligence</span>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
