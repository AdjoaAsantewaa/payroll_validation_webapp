import { type ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

interface NavItem {
  label: string;
  to: string;
  badge?: number;
}

interface ShellProps {
  breadcrumb?: string;
  title: string;
  cycleLabel?: string;
  children: ReactNode;
  navItems: NavItem[];
}

export function Shell({ breadcrumb, title, cycleLabel, children, navItems }: ShellProps) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="flex h-screen w-full overflow-hidden bg-[#f4f5f6] text-[#111]">
      <aside className="flex w-[230px] shrink-0 flex-col bg-[#0c0d0f] text-white">
        <div className="px-5 pt-6 pb-5">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-white text-[#0c0d0f]">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                <path d="M5 13l4 4L19 7" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <div className="text-[13px] font-bold leading-tight tracking-tight">Payroll Validation</div>
          </div>
          {cycleLabel && (
            <div className="mt-1 pl-9 text-[10px] uppercase tracking-wide text-white/40">
              {cycleLabel} cycle
            </div>
          )}
        </div>

        <div className="px-5 pb-2 text-[10px] font-semibold uppercase tracking-wide text-white/35">
          Workspace
        </div>
        <nav className="flex flex-col gap-0.5 px-3">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex items-center justify-between rounded-md px-3 py-2 text-[13px] font-medium transition-colors ${
                  isActive ? "bg-white text-[#0c0d0f]" : "text-white/75 hover:bg-white/10"
                }`
              }
            >
              <span>{item.label}</span>
              {!!item.badge && (
                <span className="rounded bg-[#dc2626] px-1.5 py-[1px] text-[10px] font-bold text-white">
                  {item.badge}
                </span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="mt-auto border-t border-white/10 px-4 py-4">
          <div className="mb-3 flex overflow-hidden rounded-md border border-white/15 text-[11px] font-semibold">
            <span
              className={`flex-1 px-2 py-1 text-center ${
                user?.role === "specialist" ? "bg-white text-[#0c0d0f]" : "text-white/50"
              }`}
            >
              Specialist
            </span>
            <span
              className={`flex-1 px-2 py-1 text-center ${
                user?.role === "submitter" ? "bg-white text-[#0c0d0f]" : "text-white/50"
              }`}
            >
              Submitter
            </span>
          </div>
          <button
            onClick={() => {
              logout();
              navigate("/login");
            }}
            className="flex w-full items-center gap-2 rounded-md px-1 py-1 text-left hover:bg-white/5"
          >
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-white/15 text-[11px] font-bold">
              {user?.initials}
            </span>
            <span className="flex flex-col leading-tight">
              <span className="text-[12px] font-semibold">{user?.name}</span>
              <span className="text-[10px] text-white/45">
                {user?.role === "specialist" ? "Specialist" : user?.department}
              </span>
            </span>
            <svg className="ml-auto" width="12" height="12" viewBox="0 0 24 24" fill="none">
              <path d="M15 3h6v6M21 3l-9 9M10 5H5a2 2 0 00-2 2v12a2 2 0 002 2h12a2 2 0 002-2v-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" opacity="0.5" />
            </svg>
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-[#e6e6e6] bg-white px-6">
          <div className="text-[13px] text-[#8a8a8a]">
            {breadcrumb ? (
              <span>
                {breadcrumb} <span className="mx-1">/</span>{" "}
                <span className="font-medium text-[#111]">{title}</span>
              </span>
            ) : (
              <span className="font-medium text-[#111]">{title}</span>
            )}
          </div>
          {cycleLabel && (
            <div className="flex items-center gap-3">
              <div className="rounded-md border border-[#e0e0e0] px-3 py-1.5 text-[12px] font-medium text-[#333]">
                Cycle: {cycleLabel}
              </div>
            </div>
          )}
        </header>
        <main className="flex-1 overflow-y-auto px-8 py-6">{children}</main>
      </div>
    </div>
  );
}
