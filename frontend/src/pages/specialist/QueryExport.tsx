import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Shell } from "../../components/Shell";
import { api, ApiError } from "../../api/client";
import { useAuth } from "../../context/AuthContext";
import type { DashboardData } from "../../types";

interface DraftResponse {
  to_emails: string;
  subject: string;
  body: string;
  exception_ids: number[];
  source: string;
}

interface ExportItem {
  submission_id: number;
  department: string;
  department_id: number;
  rows: number;
  state: string;
}

interface ExportPreview {
  cycle: string;
  ready_department_count: number;
  ready_row_count: number;
  items: ExportItem[];
}

export default function QueryExport() {
  const { user } = useAuth();
  const [params] = useSearchParams();
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [deptId, setDeptId] = useState<number | null>(
    params.get("department_id") ? Number(params.get("department_id")) : null
  );
  const [draft, setDraft] = useState<DraftResponse | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [toEmails, setToEmails] = useState("");
  const [sending, setSending] = useState(false);
  const [sentMsg, setSentMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [preview, setPreview] = useState<ExportPreview | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [format, setFormat] = useState<"csv" | "excel">("csv");
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    api.get<DashboardData>("/dashboard").then((d) => {
      setDashboard(d);
      if (!deptId) {
        const withOpen = d.departments.find((x) => x.exceptions > 0);
        if (withOpen) setDeptId(withOpen.department_id);
      }
    });
    loadPreview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadPreview() {
    const p = await api.get<ExportPreview>("/export/preview");
    setPreview(p);
    setSelected(new Set(p.items.filter((i) => i.state === "APPROVED").map((i) => i.submission_id)));
  }

  async function loadDraft(id: number) {
    setError(null);
    setSentMsg(null);
    try {
      const d = await api.post<DraftResponse>("/queries/draft", { department_id: id });
      setDraft(d);
      setSubject(d.subject);
      setBody(d.body);
      setToEmails(d.to_emails);
    } catch (err) {
      setDraft(null);
      setError(err instanceof ApiError ? err.message : "No open exceptions for this department.");
    }
  }

  useEffect(() => {
    if (deptId) loadDraft(deptId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deptId]);

  const deptOptions = useMemo(
    () => dashboard?.departments.filter((d) => d.exceptions > 0) || [],
    [dashboard]
  );

  async function sendQuery() {
    if (!deptId || !draft) return;
    setSending(true);
    setError(null);
    try {
      await api.post("/queries/send", {
        department_id: deptId,
        to_emails: toEmails,
        subject,
        body,
        exception_ids: draft.exception_ids,
      });
      setSentMsg("Query sent to department.");
      setDraft(null);
      const d = await api.get<DashboardData>("/dashboard");
      setDashboard(d);
      await loadPreview();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setSending(false);
    }
  }

  function toggleSelect(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function doExport() {
    if (selected.size === 0) return;
    setExporting(true);
    try {
      const res = await api.raw("/export", {
        method: "POST",
        body: JSON.stringify({ submission_ids: Array.from(selected), file_format: format }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Export failed");
      }
      const blob = await res.blob();
      const disposition = res.headers.get("content-disposition") || "";
      const match = disposition.match(/filename="(.+)"/);
      const filename = match ? match[1] : `payroll_export.${format === "excel" ? "xlsx" : "csv"}`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  const selectedRowTotal = useMemo(() => {
    if (!preview) return 0;
    return preview.items
      .filter((i) => selected.has(i.submission_id))
      .reduce((sum, i) => sum + i.rows, 0);
  }, [preview, selected]);

  return (
    <Shell
      breadcrumb="Exceptions"
      title="Query & export"
      cycleLabel={dashboard?.cycle.label}
      navItems={navItems(dashboard?.pipeline.resolve || 0, user?.is_admin)}
    >
      <h1 className="mb-1 text-[20px] font-bold tracking-tight">Query & export · {dashboard?.cycle.label}</h1>
      <p className="mb-5 text-[13px] text-[#8a8a8a]">
        Review the AI draft, edit anything, then send — or export what's already clean.
      </p>

      {error && (
        <div className="mb-4 rounded-md bg-[#fdecec] px-3 py-2 text-[12px] text-[#b91c1c]">{error}</div>
      )}
      {sentMsg && (
        <div className="mb-4 rounded-md bg-[#e8f5ec] px-3 py-2 text-[12px] text-[#15803d]">{sentMsg}</div>
      )}

      <div className="grid grid-cols-[1fr_360px] gap-4">
        <div className="card p-5">
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-[13px] font-semibold">Correction request</span>
              <select
                className="rounded border border-[#e0e0e0] px-2 py-1 text-[12px]"
                value={deptId ?? ""}
                onChange={(e) => setDeptId(Number(e.target.value))}
              >
                <option value="" disabled>
                  Select department…
                </option>
                {deptOptions.map((d) => (
                  <option key={d.department_id} value={d.department_id}>
                    {d.department} ({d.exceptions})
                  </option>
                ))}
              </select>
            </div>
            {draft && <span className="badge badge-blue">AI draft · edit before sending</span>}
          </div>

          {!draft ? (
            <div className="py-10 text-center text-[13px] text-[#8a8a8a]">
              No open exceptions to query for this department.
            </div>
          ) : (
            <>
              <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-[#8a8a8a]">
                To
              </label>
              <input className="input mb-3" value={toEmails} onChange={(e) => setToEmails(e.target.value)} />

              <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-[#8a8a8a]">
                Subject
              </label>
              <input className="input mb-3" value={subject} onChange={(e) => setSubject(e.target.value)} />

              <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-[#8a8a8a]">
                Message
              </label>
              <textarea
                className="input mb-4"
                rows={12}
                value={body}
                onChange={(e) => setBody(e.target.value)}
              />

              <div className="flex justify-end gap-2">
                <button className="btn btn-outline">Save draft</button>
                <button className="btn btn-dark" disabled={sending} onClick={sendQuery}>
                  {sending ? "Sending…" : "Send query"}
                </button>
              </div>
            </>
          )}
        </div>

        <div className="card p-5">
          <div className="mb-1 text-[13px] font-semibold">Export clean dataset</div>
          <p className="mb-3 text-[11px] text-[#8a8a8a]">
            Only approved departments are included. Unresolved departments stay behind for the next
            export.
          </p>

          <div className="mb-4 flex flex-col gap-1.5">
            {preview?.items.map((item) => {
              const approved = item.state === "APPROVED";
              return (
                <label
                  key={item.submission_id}
                  className={`flex items-center justify-between rounded-md border px-2.5 py-2 text-[12px] ${
                    approved ? "border-[#e6e6e6]" : "border-[#f1f1f1] opacity-60"
                  }`}
                >
                  <span className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      disabled={!approved}
                      checked={selected.has(item.submission_id)}
                      onChange={() => toggleSelect(item.submission_id)}
                    />
                    {item.department}
                  </span>
                  <span className="flex items-center gap-2 text-[#8a8a8a]">
                    <span>{item.rows || "—"} rows</span>
                    <span
                      className={`badge ${
                        approved ? "badge-green" : item.state === "0 EXCEPTIONS" ? "badge-grey" : "badge-amber"
                      }`}
                    >
                      {item.state}
                    </span>
                  </span>
                </label>
              );
            })}
          </div>

          <div className="mb-3 flex gap-2">
            {(["csv", "excel"] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFormat(f)}
                className={`rounded-full px-3 py-1 text-[11px] font-semibold ${
                  format === f ? "bg-[#111] text-white" : "bg-[#f0f0f0] text-[#555]"
                }`}
              >
                {f.toUpperCase()}
              </button>
            ))}
          </div>

          <div className="mb-3 text-[13px]">
            <span className="text-[22px] font-bold">{selectedRowTotal}</span>{" "}
            <span className="text-[#8a8a8a]">rows across {selected.size} department(s) ready</span>
          </div>

          <button
            className="btn btn-dark w-full py-2.5"
            disabled={selected.size === 0 || exporting}
            onClick={doExport}
          >
            {exporting ? "Exporting…" : `Export ${selectedRowTotal} rows`}
          </button>

          <p className="mt-3 text-[10px] text-[#999]">
            Every export writes user, time, row count and file hash to the audit log.
          </p>
        </div>
      </div>
    </Shell>
  );
}

function navItems(count: number, isAdmin?: boolean) {
  const items = [
    { label: "Dashboard", to: "/dashboard" },
    { label: "Exceptions", to: "/exceptions", badge: count },
    { label: "Query & export", to: "/query-export" },
  ];
  if (isAdmin) items.push({ label: "Admin", to: "/admin/submitters" });
  return items;
}
