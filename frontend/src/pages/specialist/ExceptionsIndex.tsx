import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Shell } from "../../components/Shell";
import { StatusBadge } from "../../components/StatusBadge";
import { api } from "../../api/client";
import type { DashboardData } from "../../types";

export default function ExceptionsIndex() {
  const [data, setData] = useState<DashboardData | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.get<DashboardData>("/dashboard").then(setData);
  }, []);

  if (!data) {
    return (
      <Shell title="Exceptions" navItems={navItems(0)}>
        <div className="text-sm text-[#8a8a8a]">Loading…</div>
      </Shell>
    );
  }

  const withExceptions = data.departments.filter((d) => d.rows > 0);

  return (
    <Shell title="Exceptions" cycleLabel={data.cycle.label} navItems={navItems(data.pipeline.resolve)}>
      <h1 className="mb-1 text-[20px] font-bold tracking-tight">Exceptions by department</h1>
      <p className="mb-5 text-[13px] text-[#8a8a8a]">Pick a department to review its flagged rows.</p>

      <div className="card overflow-hidden">
        <table className="table-clean">
          <thead>
            <tr>
              <th>Department</th>
              <th>Status</th>
              <th>Rows</th>
              <th>Exceptions</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {withExceptions.map((dep) => (
              <tr key={dep.submission_id}>
                <td className="font-medium">{dep.department}</td>
                <td>
                  <StatusBadge status={dep.status} />
                </td>
                <td>{dep.rows}</td>
                <td>
                  {dep.exceptions > 0 ? (
                    <span className="font-semibold text-[#b91c1c]">{dep.exceptions}</span>
                  ) : (
                    <span className="text-[#8a8a8a]">0</span>
                  )}
                </td>
                <td className="text-right">
                  <button
                    onClick={() => navigate(`/exceptions/${dep.submission_id}`)}
                    className="btn btn-ghost px-2 py-1 text-[12px]"
                  >
                    Open →
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}

function navItems(count: number) {
  return [
    { label: "Dashboard", to: "/dashboard" },
    { label: "Exceptions", to: "/exceptions", badge: count },
    { label: "Query & export", to: "/query-export" },
  ];
}
