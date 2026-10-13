import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../auth";

const link = ({ isActive }: { isActive: boolean }) =>
  `whitespace-nowrap rounded-md px-3 py-1.5 text-sm ${isActive ? "bg-emerald-100 text-emerald-900" : "text-slate-600"}`;

export function AppShell({ children, wide = false }: { children: ReactNode; wide?: boolean }) {
  const { user, logout } = useAuth();
  const width = wide ? "max-w-6xl" : "max-w-3xl";
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className={`mx-auto flex items-center justify-between gap-3 px-4 pt-3 ${width}`}>
          <div className="min-w-0">
            <p className="whitespace-nowrap font-semibold text-emerald-800">Kanakku AI</p>
            <p className="truncate text-xs text-slate-500">{user?.business_name}</p>
          </div>
          <button onClick={() => void logout()} className="whitespace-nowrap rounded-md border border-slate-300 px-3 py-1.5 text-sm">
            Log out
          </button>
        </div>
        <nav aria-label="Main" className={`mx-auto flex gap-1 overflow-x-auto px-3 py-2 ${width}`}>
          <NavLink to="/" end className={link}>Home</NavLink>
          <NavLink to="/bills" className={link}>Bills</NavLink>
          <NavLink to="/ledger" className={link}>Ledger</NavLink>
          <NavLink to="/ask" className={link}>Ask GST</NavLink>
          <NavLink to="/followups" className={link}>Follow-ups</NavLink>
          <NavLink to="/account" className={link}>Account</NavLink>
        </nav>
      </header>
      <main className={`mx-auto w-full px-4 py-6 ${width}`}>{children}</main>
    </div>
  );
}
