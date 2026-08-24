import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Shell } from "../../components/Shell";
import { SeverityBadge, SourceBadge } from "../../components/StatusBadge";
import { api, ApiError } from "../../api/client";
import type { ExceptionItem } from "../../types";

interface ListResponse {
  submission: { id: number; department: string; department_id: number; row_count: number; status: string } | null;
  exceptions: ExceptionItem[];
  counts: { all: number; high: number; med: number; low: number };
}

type SevFilter = "all" | "high" | "med" | "low";

export default function ExceptionReview() {
  const { submissionId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState<ListResponse | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [filter, setFilter] = useState<SevFilter>("all");
  const [note, setNote] = useState("");
  const [rowDetail, setRowDetail] = useState<ExceptionItem["row"] | null>(null);
  const [history, setHistory] = useState<number[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    const d = await api.get<ListResponse>(`/exceptions?submission_id=${submissionId}`);
    setData(d);
    const openOnes = d.exceptions.filter((e) => e.status === "open" || e.status === "query_open");
    setSelectedId((prev) => prev ?? openOnes[0]?.id ?? d.exceptions[0]?.id ?? null);
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [submissionId]);

  useEffect(() => {
    setNote("");
    setHistory(null);
    setRowDetail(null);
    if (selectedId) {
      api.get<ExceptionItem>(`/exceptions/${selectedId}`).then((d) => setRowDetail(d.row ?? null));
    }
  }, [selectedId]);

  const filtered = useMemo(() => {
    if (!data) return [];
    if (filter === "all") return data.exceptions;
    return data.exceptions.filter((e) => e.severity === filter);
  }, [data, filter]);

  const selected = data?.exceptions.find((e) => e.id === selectedId) || null;
  const hasComparisonData =
    !!selected &&
    (selected.submitted_value !== null ||
      (rowDetail?.basic_pay !== null && rowDetail?.basic_pay !== undefined) ||
      (rowDetail?.allowances !== null && rowDetail?.allowances !== undefined));

  async function decide(action: "accept" | "reject" | "query") {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      await api.post(`/exceptions/${selected.id}/${action === "accept" ? "accept" : action === "reject" ? "reject" : "query"}`, {
        note: note || null,
      });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    if (!data?.submission) return;
    setBusy(true);
    setError(null);
    try {
      await api.post(`/submissions/${data.submission.id}/approve`);
      navigate("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  async function loadHistory() {
    if (!selected) return;
    const h = await api.get<{ periods: number[] }>(`/exceptions/${selected.id}/history`);
    setHistory(h.periods);
  }

  if (!data) {
    return (
      <Shell breadcrumb="Dashboard" title="Exceptions" navItems={navItems(0)}>
        <div className="text-sm text-[#8a8a8a]">Loading…</div>
      </Shell>
    );
  }

  const sub = data.submission;

  return (
    <Shell
      breadcrumb="Dashboard"
      title="Exceptions"
      navItems={navItems(data.counts.all)}
    >
      <div className="mb-4 flex items-start justify-between">
        <div>
          <button onClick={() => navigate("/dashboard")} className="mb-1 text-[12px] text-[#8a8a8a] hover:text-[#111]">
            ← Dashboard
          </button>
          <h1 className="text-[20px] font-bold tracking-tight">
            {sub?.department} · Exception review
          </h1>
          <p className="mt-0.5 text-[13px] text-[#8a8a8a]">
            {sub?.row_count} rows · {data.counts.all} exceptions
          </p>
        </div>
        <div className="flex gap-2">
          <button
            className="btn btn-outline"
            disabled={!sub}
            onClick={() => sub && navigate(`/query-export?department_id=${sub.department_id}`)}
          >
            Send query to department
          </button>
          <button className="btn btn-dark" disabled={busy} onClick={approve}>
            Approve submission
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-md bg-[#fdecec] px-3 py-2 text-[12px] text-[#b91c1c]">
          {error}
        </div>
      )}

      <div className="grid grid-cols-[380px_1fr] gap-4">
        <div className="card overflow-hidden">
          <div className="flex gap-1 border-b border-[#eee] p-2">
            {(["all", "high", "med", "low"] as SevFilter[]).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                  filter === f ? "bg-[#111] text-white" : "bg-[#f0f0f0] text-[#555]"
                }`}
              >
                {f === "all" ? `All ${data.counts.all}` : `${f[0].toUpperCase()}${f.slice(1)} ${data.counts[f]}`}
              </button>
            ))}
          </div>
          <div className="max-h-[calc(100vh-260px)] overflow-y-auto">
            {filtered.map((e) => (
              <button
                key={e.id}
                onClick={() => setSelectedId(e.id)}
                className={`block w-full border-b border-[#f2f2f2] px-3 py-2.5 text-left transition-colors ${
                  selectedId === e.id ? "border-l-[3px] border-l-[#dc2626] bg-[#fdf6f6] pl-[9px]" : "hover:bg-[#fafafa]"
                }`}
              >
                <div className="mb-1 flex items-center gap-1.5">
                  <SeverityBadge severity={e.severity} />
                  <SourceBadge source={e.source} />
                  {e.status !== "open" && (
                    <span className="ml-auto text-[10px] font-medium text-[#8a8a8a]">
                      {e.status.replace("_", " ")}
                    </span>
                  )}
                </div>
                <div className="text-[12.5px] font-semibold text-[#222]">{e.row_label}</div>
                <div className="mt-0.5 text-[12px] text-[#666]">{e.issue_text}</div>
              </button>
            ))}
            {filtered.length === 0 && (
              <div className="p-4 text-center text-[12px] text-[#999]">No exceptions in this filter.</div>
            )}
          </div>
        </div>

        <div className="card p-5">
          {!selected ? (
            <div className="text-[13px] text-[#8a8a8a]">Select an exception from the list.</div>
          ) : (
            <>
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <SeverityBadge severity={selected.severity} />
                  <h2 className="mt-1.5 text-[16px] font-bold">{selected.row_label}</h2>
                </div>
              </div>

              {hasComparisonData && (
                <table className="table-clean mb-4">
                  <thead>
                    <tr>
                      <th>Field</th>
                      <th>Submitted</th>
                      <th>Usual</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selected.submitted_value !== null && (
                      <tr>
                        <td className="font-medium">{selected.field}</td>
                        <td className={selected.severity === "high" ? "font-semibold text-[#b91c1c]" : ""}>
                          {selected.submitted_value}
                        </td>
                        <td className="text-[#8a8a8a]">{selected.usual_value ?? "—"}</td>
                      </tr>
                    )}
                    {rowDetail?.basic_pay !== null && rowDetail?.basic_pay !== undefined && selected.field !== "basic_pay" && (
                      <tr>
                        <td>basic_pay</td>
                        <td>{rowDetail.basic_pay}</td>
                        <td className="text-[#8a8a8a]">{rowDetail.basic_pay}</td>
                      </tr>
                    )}
                    {rowDetail?.allowances !== null && rowDetail?.allowances !== undefined && selected.field !== "allowances" && (
                      <tr>
                        <td>allowances</td>
                        <td>{rowDetail.allowances}</td>
                        <td className="text-[#8a8a8a]">{rowDetail.allowances}</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              )}

              {selected.ai_explanation && (
                <div className="mb-4 rounded-md border border-[#cfe0fb] bg-[#f3f7ff] p-3.5">
                  <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-[#1d4ed8]">
                    AI explanation
                  </div>
                  <p className="text-[13px] leading-relaxed text-[#1e293b]">{selected.ai_explanation}</p>
                  {selected.recommended_action && (
                    <p className="mt-1 text-[12px] text-[#475569]">
                      Recommended: {selected.recommended_action}
                    </p>
                  )}
                  <div className="mt-2 flex gap-3 text-[11px] font-medium text-[#1d4ed8]">
                    <button onClick={loadHistory} className="hover:underline">
                      See last 6 periods
                    </button>
                  </div>
                  {history && (
                    <div className="mt-2 flex items-end gap-1">
                      {history.map((v, i) => (
                        <div key={i} className="flex flex-col items-center gap-0.5">
                          <div
                            className="w-4 rounded-t bg-[#93b8f5]"
                            style={{ height: `${Math.max(4, v * 2)}px` }}
                          />
                          <span className="text-[9px] text-[#94a3b8]">{v}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {!selected.ai_explanation && !hasComparisonData && (
                <div className="mb-4 rounded-md bg-[#f6f6f6] p-3.5 text-[13px] text-[#555]">
                  {selected.issue_text}
                  {selected.usual_value && (
                    <div className="mt-1 text-[12px] text-[#8a8a8a]">{selected.usual_value}</div>
                  )}
                </div>
              )}

              <div className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-[#8a8a8a]">
                Decision
              </div>
              {selected.status !== "open" ? (
                <div className="mb-3 rounded-md bg-[#f6f6f6] px-3 py-2 text-[12px] text-[#555]">
                  Marked <strong>{selected.status.replace("_", " ")}</strong>
                  {selected.note ? ` — "${selected.note}"` : ""}
                </div>
              ) : (
                <div className="mb-3 flex gap-2">
                  <button className="btn btn-outline flex-1" disabled={busy} onClick={() => decide("accept")}>
                    Accept as correct
                  </button>
                  <button className="btn btn-outline flex-1" disabled={busy} onClick={() => decide("reject")}>
                    Reject row
                  </button>
                  <button className="btn btn-dark flex-1" disabled={busy} onClick={() => decide("query")}>
                    Add to query
                  </button>
                </div>
              )}
              <textarea
                className="input"
                rows={2}
                placeholder="Note for the audit trail (optional)…"
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </>
          )}
        </div>
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
