import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Shell } from "../../components/Shell";
import { api } from "../../api/client";
import type { ExceptionItem } from "../../types";

interface StatusResponse {
  cycle: { label: string; cutoff_date: string };
  department: string;
  submission: {
    id: number | null;
    status: string;
    row_count: number;
    self_fixed_count: number;
    uploaded_at: string | null;
    filename: string | null;
  };
  open_questions: ExceptionItem[];
  earlier_cycles: { cycle: string; rows: number; outcome: string }[];
}

export default function Status() {
  const [data, setData] = useState<StatusResponse | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.get<StatusResponse>("/submissions/status").then(setData);
  }, []);

  if (!data) {
    return (
      <Shell title="Status" navItems={navItems()}>
        <div className="text-sm text-[#8a8a8a]">Loading…</div>
      </Shell>
    );
  }

  const { submission } = data;
  const hasUpload = !!submission.uploaded_at;

  return (
    <Shell title="Status" navItems={navItems()}>
      <h1 className="mb-1 text-[20px] font-bold tracking-tight">{data.cycle.label}</h1>
      <p className="mb-5 text-[13px] text-[#8a8a8a]">{data.department}</p>

      <div className="grid grid-cols-[1fr_320px] gap-4">
        <div className="card p-5">
          {!hasUpload ? (
            <div className="py-8 text-center text-[13px] text-[#8a8a8a]">
              No file uploaded for this cycle yet.
              <div className="mt-3">
                <button className="btn btn-dark" onClick={() => navigate("/submitter/upload")}>
                  Upload cycle
                </button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              <TimelineStep label="Uploaded" detail={formatTime(submission.uploaded_at)} />
              <TimelineStep
                label="Checked"
                detail={`${submission.row_count} rows`}
              />
              {submission.self_fixed_count > 0 && (
                <TimelineStep label="You fixed" detail={`${submission.self_fixed_count}`} />
              )}
              <div className="mt-2">
                <button className="btn btn-outline" onClick={() => navigate("/submitter/upload")}>
                  Go to upload
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="card p-5">
          <div className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-[#8a8a8a]">
            With payroll
          </div>
          {data.open_questions.length === 0 ? (
            <div className="rounded-md border border-dashed border-[#d8d8d8] px-3 py-4 text-center text-[12px] text-[#8a8a8a]">
              Nothing else needed from you.
              <div className="mt-1 text-[11px]">You'll be emailed if that changes.</div>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {data.open_questions.map((q) => (
                <div key={q.id} className="rounded-md border border-[#f6dfae] bg-[#fdf7ec] px-3 py-2.5">
                  <div className="mb-1 text-[12.5px] font-semibold">{q.row_label}</div>
                  <div className="mb-2 text-[12px] text-[#555]">{q.issue_text}</div>
                  <button
                    className="btn btn-dark w-full py-1.5 text-[11px]"
                    onClick={() => navigate(`/submitter/answer/${q.id}`)}
                  >
                    Answer
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="mt-6">
        <div className="mb-2 text-[12px] font-semibold text-[#333]">Earlier cycles</div>
        <div className="card overflow-hidden">
          <table className="table-clean">
            <thead>
              <tr>
                <th>Cycle</th>
                <th>Rows</th>
                <th>Outcome</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.earlier_cycles.length === 0 && (
                <tr>
                  <td colSpan={4} className="py-4 text-center text-[#999]">
                    No earlier cycles yet.
                  </td>
                </tr>
              )}
              {data.earlier_cycles.map((c) => (
                <tr key={c.cycle}>
                  <td>{c.cycle}</td>
                  <td>{c.rows}</td>
                  <td className="text-[#8a8a8a]">{c.outcome}</td>
                  <td className="text-right text-[#1d4ed8]">
                    <span className="cursor-pointer hover:underline">View file</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Shell>
  );
}

function TimelineStep({ label, detail }: { label: string; detail: string }) {
  return (
    <div className="flex items-center gap-3 rounded-md bg-[#0c0d0f] px-3 py-2.5 text-white">
      <div className="text-[12.5px] font-semibold">{label}</div>
      <div className="ml-auto text-[11px] text-white/60">{detail}</div>
    </div>
  );
}

function formatTime(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-GB", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "short" });
}

function navItems() {
  return [
    { label: "Status", to: "/submitter/status" },
    { label: "Upload cycle", to: "/submitter/upload" },
  ];
}
