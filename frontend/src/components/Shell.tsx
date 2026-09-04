import { type ReactNode, useEffect, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
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
  const location = useLocation();
  const [navOpen, setNavOpen] = useState(false);

  // Close the mobile drawer on every navigation so it never stays open
  // behind the next page.
  useEffect(() => {
    setNavOpen(false);
  }, [location.pathname]);

  return (
    <div className="flex h-screen w-full overflow-hidden bg-[#f4f5f6] text-[#111]">
      {navOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/40 lg:hidden"
          onClick={() => setNavOpen(false)}
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-[230px] shrink-0 flex-col bg-[#0c0d0f] text-white transition-transform duration-200 lg:static lg:translate-x-0 ${
          navOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="px-5 pt-6 pb-5">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-white text-[#0c0d0f]">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                <path d="M5 13l4 4L19 7" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <div className="text-[13px] font-bold leading-tight tracking-tight">Payroll Validation</div>
            <button
              onClick={() => setNavOpen(false)}
              className="ml-auto text-white/60 hover:text-white lg:hidden"
              aria-label="Close menu"
            >
              ✕
            </button>
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
          {user?.role === "admin" ? (
            <div className="mb-3 overflow-hidden rounded-md border border-white/15 bg-white px-2 py-1 text-center text-[11px] font-semibold text-[#0c0d0f]">
              Admin
            </div>
          ) : (
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
          )}
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
                {user?.role === "specialist"
                  ? "Specialist"
                  : user?.role === "admin"
                    ? "Admin"
                    : user?.department}
              </span>
            </span>
            <svg className="ml-auto" width="12" height="12" viewBox="0 0 24 24" fill="none">
              <path d="M15 3h6v6M21 3l-9 9M10 5H5a2 2 0 00-2 2v12a2 2 0 002 2h12a2 2 0 002-2v-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" opacity="0.5" />
            </svg>
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-[#e6e6e6] bg-white px-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <button
              onClick={() => setNavOpen(true)}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-[#333] hover:bg-[#f4f5f6] lg:hidden"
              aria-label="Open menu"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path d="M4 6h16M4 12h16M4 18h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </button>
            <div className="min-w-0 truncate text-[13px] text-[#8a8a8a]">
              {breadcrumb ? (
                <span>
                  {breadcrumb} <span className="mx-1">/</span>{" "}
                  <span className="font-medium text-[#111]">{title}</span>
                </span>
              ) : (
                <span className="font-medium text-[#111]">{title}</span>
              )}
            </div>
          </div>
          {cycleLabel && (
            <div className="flex shrink-0 items-center gap-3">
              <div className="whitespace-nowrap rounded-md border border-[#e0e0e0] px-2.5 py-1.5 text-[11px] font-medium text-[#333] sm:px-3 sm:text-[12px]">
                Cycle: {cycleLabel}
              </div>
            </div>
          )}
        </header>
        <main className="flex-1 overflow-y-auto overflow-x-hidden px-4 py-5 sm:px-6 lg:px-8 lg:py-6">{children}</main>
      </div>
    </div>
  );
}
