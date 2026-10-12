import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../auth";

const link = ({ isActive }: { isActive: boolean }) =>
  `whitespace-nowrap rounded-md px-2 py-1.5 text-sm sm:px-3 ${isActive ? "bg-emerald-100 text-emerald-900" : "text-slate-600"}`;

export function AppShell({ children, wide = false }: { children: ReactNode; wide?: boolean }) {
  const { user, logout } = useAuth();
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className={`mx-auto flex items-center justify-between gap-3 px-4 py-3 ${wide ? "max-w-6xl" : "max-w-3xl"}`}>
          <div className="min-w-0">
            <p className="whitespace-nowrap font-semibold text-emerald-800">Kanakku AI</p>
            <p className="truncate text-xs text-slate-500">{user?.business_name}</p>
          </div>
          <nav className="flex shrink-0 items-center gap-0.5 sm:gap-1">
            <NavLink to="/" end className={link}>Home</NavLink>
            <NavLink to="/bills" className={link}>Bills</NavLink>
            <NavLink to="/ask" className={link}>Ask GST</NavLink>
            <button onClick={() => void logout()} className="ml-1 whitespace-nowrap rounded-md border border-slate-300 px-2 py-1.5 text-sm sm:px-3">
              Log out
            </button>
          </nav>
        </div>
      </header>
      <main className={`mx-auto w-full px-4 py-6 ${wide ? "max-w-6xl" : "max-w-3xl"}`}>{children}</main>
    </div>
  );
}
