import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Shell } from "../../components/Shell";
import { StatusBadge } from "../../components/StatusBadge";
import { api } from "../../api/client";
import type { DashboardData } from "../../types";

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  async function load() {
    setLoading(true);
    const d = await api.get<DashboardData>("/dashboard");
    setData(d);
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, []);

  if (loading || !data) {
    return (
      <Shell title="Dashboard" navItems={navItems(0)}>
        <div className="text-sm text-[#8a8a8a]">Loading…</div>
      </Shell>
    );
  }

  const pipeline = [
    { label: "Submit", value: data.pipeline.submitted },
    { label: "Mapped", value: data.pipeline.mapped },
    { label: "Validated", value: data.pipeline.validated },
    { label: "Resolve", value: data.pipeline.resolve, highlight: true },
    { label: "Approve", value: data.pipeline.approve },
    { label: "Export", value: data.pipeline.export },
  ];

  const maxChart = Math.max(1, ...data.chart.map((c) => c.count));

  function actionFor(dep: DashboardData["departments"][number]) {
    switch (dep.status) {
      case "needs_review":
        return { label: "Review →", onClick: () => navigate(`/exceptions/${dep.submission_id}`) };
      case "query_sent":
        return { label: "Open →", onClick: () => navigate(`/exceptions/${dep.submission_id}`) };
      case "approved":
        return { label: "View", onClick: () => navigate(`/exceptions/${dep.submission_id}`) };
      default:
        return { label: "Remind", onClick: () => alert(`Reminder sent to ${dep.department}.`) };
    }
  }

  return (
    <Shell
      title="Dashboard"
      cycleLabel={data.cycle.label}
      navItems={navItems(data.pipeline.resolve)}
    >
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-[22px] font-bold tracking-tight">{data.cycle.label} cycle</h1>
          <p className="mt-1 text-[13px] text-[#8a8a8a]">
            Cut-off {formatCutoff(data.cycle.cutoff_date)} · {data.pipeline.total_departments}{" "}
            departments · every department at a glance
          </p>
        </div>
        <div className="flex gap-2">
          <button className="btn btn-outline">Payroll schema</button>
          <button className="btn btn-dark" onClick={() => navigate("/query-export")}>
            Export clean data
          </button>
        </div>
      </div>

      <div className="mb-6 grid grid-cols-6 gap-3">
        {pipeline.map((p) => (
          <div
            key={p.label}
            className={`card px-4 py-3 ${p.highlight ? "border-[#f0b4ac] bg-[#fdf3f2]" : ""}`}
          >
            <div className="text-[22px] font-bold leading-none">{p.value}</div>
            <div
              className={`mt-1.5 text-[10px] font-semibold uppercase tracking-wide ${
                p.highlight ? "text-[#b91c1c]" : "text-[#8a8a8a]"
              }`}
            >
              {p.label}
            </div>
          </div>
        ))}
      </div>

      <div className="mb-6 grid grid-cols-4 gap-3">
        <div className="card border-[#f0b4ac] bg-[#fdf3f2] px-4 py-3.5">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-[#b91c1c]">
            Needs you
          </div>
          <div className="mt-1 text-[26px] font-bold leading-none">{data.stats.needs_you}</div>
          <div className="mt-1 text-[11px] text-[#c05f56]">Exceptions unresolved</div>
        </div>
        <div className="card px-4 py-3.5">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-[#8a8a8a]">
            Submitted
          </div>
          <div className="mt-1 text-[26px] font-bold leading-none">
            {data.stats.submitted_of_total}
          </div>
          <div className="mt-1 text-[11px] text-[#8a8a8a]">
            {data.stats.not_in_yet} department{data.stats.not_in_yet === 1 ? "" : "s"} not in yet
          </div>
        </div>
        <div className="card px-4 py-3.5">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-[#8a8a8a]">
            Self-fixed
          </div>
          <div className="mt-1 text-[26px] font-bold leading-none">{data.stats.self_fixed}</div>
          <div className="mt-1 text-[11px] text-[#8a8a8a]">Resolved without you</div>
        </div>
        <div className="card px-4 py-3.5">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-[#8a8a8a]">
            Approved
          </div>
          <div className="mt-1 text-[26px] font-bold leading-none">{data.stats.approved}</div>
          <div className="mt-1 text-[11px] text-[#8a8a8a]">Ready to export</div>
        </div>
      </div>

      <div className="card mb-6 px-5 py-4">
        <div className="mb-3 text-[12px] font-semibold text-[#333]">
          Exceptions by department · this cycle
        </div>
        <div className="flex flex-col gap-2">
          {data.chart.map((c) => (
            <div key={c.department} className="flex items-center gap-3">
              <div className="w-20 shrink-0 text-[12px] text-[#444]">{c.department}</div>
              <div className="h-3 flex-1 overflow-hidden rounded bg-[#f0f0f0]">
                <div
                  className="h-full rounded bg-[#2b6cee]"
                  style={{ width: `${(c.count / maxChart) * 100}%`, opacity: c.count === 0 ? 0.15 : 1 }}
                />
              </div>
              <div className="w-6 text-right text-[12px] font-medium text-[#444]">{c.count}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="card overflow-hidden">
        <table className="table-clean">
          <thead>
            <tr>
              <th>Department</th>
              <th>Status</th>
              <th>Rows</th>
              <th>Exceptions</th>
              <th>Last activity</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data.departments.map((dep) => {
              const action = actionFor(dep);
              return (
                <tr key={dep.submission_id}>
                  <td className="font-medium">{dep.department}</td>
                  <td>
                    <StatusBadge status={dep.status} />
                  </td>
                  <td>{dep.rows || "—"}</td>
                  <td>
                    {dep.exceptions > 0 ? (
                      <span>
                        <span className="font-semibold text-[#b91c1c]">{dep.exceptions}</span>
                        {dep.exceptions_high > 0 && (
                          <span className="text-[#8a8a8a]"> · {dep.exceptions_high} high</span>
                        )}
                      </span>
                    ) : (
                      <span className="text-[#8a8a8a]">0</span>
                    )}
                  </td>
                  <td className="text-[#8a8a8a]">{dep.last_activity || "—"}</td>
                  <td className="text-right">
                    <button onClick={action.onClick} className="btn btn-ghost px-2 py-1 text-[12px]">
                      {action.label}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}

function formatCutoff(iso: string) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
}

function navItems(resolveCount: number) {
  return [
    { label: "Dashboard", to: "/dashboard" },
    { label: "Exceptions", to: "/exceptions", badge: resolveCount },
    { label: "Query & export", to: "/query-export" },
  ];
}
