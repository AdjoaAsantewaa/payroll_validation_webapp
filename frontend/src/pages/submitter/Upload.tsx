import { useEffect, useRef, useState } from "react";
import { Shell } from "../../components/Shell";
import { SeverityBadge, SourceBadge } from "../../components/StatusBadge";
import { api, ApiError } from "../../api/client";
import { useAuth } from "../../context/AuthContext";
import type { ExceptionItem } from "../../types";

const CANONICAL_FIELDS = ["staff_id", "full_name", "overtime_hours", "basic_pay", "allowances"];

interface UploadResult {
  submission_id: number;
  filename: string;
  row_count: number;
  mapping: Record<string, string | null>;
  mapping_source: string;
  unmapped_columns: string[];
  exceptions: ExceptionItem[];
  self_fixed_count: number;
}

export default function Upload() {
  const { user } = useAuth();
  const fileRef = useRef<HTMLInputElement>(null);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [uploading, setUploading] = useState(false);
  const [editingMapping, setEditingMapping] = useState(false);
  const [mappingDraft, setMappingDraft] = useState<Record<string, string | null>>({});
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [expandedRow, setExpandedRow] = useState<number | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  async function handleFile(file: File) {
    setUploading(true);
    setError(null);
    setSubmitted(false);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await api.postForm<UploadResult>("/submissions/upload", form);
      setResult(res);
      setMappingDraft(res.mapping);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }

  async function confirmMapping() {
    if (!result) return;
    setUploading(true);
    setError(null);
    try {
      const res = await api.post<{ submission_id: number; row_count: number; mapping: Record<string, string | null>; exceptions: ExceptionItem[] }>(
        `/submissions/${result.submission_id}/remap`,
        { mapping: mappingDraft }
      );
      setResult({ ...result, mapping: res.mapping, exceptions: res.exceptions, row_count: res.row_count });
      setEditingMapping(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update mapping");
    } finally {
      setUploading(false);
    }
  }

  async function submitAnyway() {
    if (!result) return;
    setUploading(true);
    try {
      await api.post(`/submissions/${result.submission_id}/submit-anyway`, { note });
      setSubmitted(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setUploading(false);
    }
  }

  const problems = result?.exceptions || [];
  const blocking = problems.filter((p) => p.source === "rule");
  const advisory = problems.filter((p) => p.source === "ai");

  return (
    <Shell title="Upload cycle" navItems={navItems()} cycleLabel={undefined}>
      <h1 className="mb-1 text-[20px] font-bold tracking-tight">
        Upload cycle · {user?.department}
      </h1>
      <p className="mb-5 text-[13px] text-[#8a8a8a]">
        One file, Excel or CSV, whatever format you already use.
      </p>

      {error && (
        <div className="mb-4 rounded-md bg-[#fdecec] px-3 py-2 text-[12px] text-[#b91c1c]">{error}</div>
      )}
      {submitted && (
        <div className="mb-4 rounded-md bg-[#e8f5ec] px-3 py-2 text-[12px] text-[#15803d]">
          Submitted for payroll review with your note.
        </div>
      )}

      <div className="card mb-4 p-5">
        <div className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-[#8a8a8a]">
          Step 1 — File
        </div>
        {!result ? (
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            onClick={() => fileRef.current?.click()}
            className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed py-10 text-center transition-colors ${
              dragOver ? "border-[#111] bg-[#fafafa]" : "border-[#d8d8d8]"
            }`}
          >
            <div className="mb-2 text-[13px] font-semibold">
              {uploading ? "Uploading…" : "Drop your file here"}
            </div>
            <div className="text-[12px] text-[#8a8a8a]">or browse</div>
            <input
              ref={fileRef}
              type="file"
              accept=".csv,.xlsx,.xls"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
            />
          </div>
        ) : (
          <div className="flex items-center justify-between rounded-md border border-[#e6e6e6] bg-[#fafafa] px-3 py-2.5">
            <div className="text-[13px]">
              <span className="font-semibold">{result.filename}</span>
              <span className="ml-2 text-[#8a8a8a]">{result.row_count} rows uploaded</span>
            </div>
            <button
              onClick={() => fileRef.current?.click()}
              className="text-[12px] font-medium text-[#8a8a8a] hover:text-[#111]"
            >
              ✕
            </button>
            <input
              ref={fileRef}
              type="file"
              accept=".csv,.xlsx,.xls"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
            />
          </div>
        )}
      </div>

      {result && (
        <div className="card mb-4 p-5">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-[#8a8a8a]">
              Step 2 — Column mapping
            </div>
            {!editingMapping ? (
              <button
                onClick={() => setEditingMapping(true)}
                className="text-[11px] font-medium text-[#1d4ed8] hover:underline"
              >
                {result.mapping_source === "ai" || result.mapping_source === "mock" ? "AI matched" : "Cached"} · edit
              </button>
            ) : (
              <button onClick={confirmMapping} className="btn btn-dark px-3 py-1 text-[11px]">
                Confirm mapping
              </button>
            )}
          </div>
          <table className="table-clean">
            <thead>
              <tr>
                <th>Your column</th>
                <th>Our field</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(result.mapping).map(([source, field]) => (
                <tr key={source}>
                  <td>{source}</td>
                  <td>
                    {editingMapping ? (
                      <select
                        className="rounded border border-[#d8d8d8] px-1.5 py-1 text-[12px]"
                        value={mappingDraft[source] ?? ""}
                        onChange={(e) =>
                          setMappingDraft((prev) => ({ ...prev, [source]: e.target.value || null }))
                        }
                      >
                        <option value="">— unmapped —</option>
                        {CANONICAL_FIELDS.map((f) => (
                          <option key={f} value={f}>
                            {f}
                          </option>
                        ))}
                      </select>
                    ) : field ? (
                      <span className="font-medium text-[#111]">{field}</span>
                    ) : (
                      <span className="font-medium text-[#b45309]">? unsure — confirm</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-[11px] text-[#8a8a8a]">Mapping is remembered for next month.</p>
        </div>
      )}

      {result && (
        <div className="card p-5">
          <div className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-[#8a8a8a]">
            Step 3 — Result (immediate)
          </div>
          {problems.length === 0 ? (
            <div className="rounded-md bg-[#e8f5ec] px-3 py-3 text-[13px] font-semibold text-[#15803d]">
              No problems found — every row looks clean.
            </div>
          ) : (
            <>
              <div className="mb-3">
                <span className="text-[20px] font-bold text-[#b91c1c]">{problems.length}</span>{" "}
                <span className="text-[13px] font-semibold">problems found</span>
                <div className="text-[12px] text-[#8a8a8a]">
                  {result.row_count - problems.length} of {result.row_count} rows fine — fix these and
                  resubmit, no one has to chase you.
                </div>
              </div>
              <div className="flex flex-col gap-2">
                {[...blocking, ...advisory].map((p) => (
                  <div
                    key={p.id}
                    className={`rounded-md border px-3 py-2.5 ${
                      p.source === "rule" ? "border-[#f4c9c3] bg-[#fdf3f2]" : "border-[#f6dfae] bg-[#fdf7ec]"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5 text-[12.5px] font-semibold">
                          {p.row_label}
                          <SeverityBadge severity={p.severity} />
                          <SourceBadge source={p.source} />
                        </div>
                        <div className="mt-0.5 text-[12.5px] text-[#444]">{p.issue_text}</div>
                        {expandedRow === p.id && (
                          <div className="mt-2 rounded bg-white/70 p-2 text-[12px] text-[#555]">
                            {p.ai_explanation || p.usual_value ? (
                              <>
                                {p.ai_explanation && <p className="mb-1">{p.ai_explanation}</p>}
                                {p.usual_value && (
                                  <p className="text-[#8a8a8a]">Usual: {p.usual_value}</p>
                                )}
                              </>
                            ) : (
                              <p className="text-[#8a8a8a]">No further detail available.</p>
                            )}
                          </div>
                        )}
                      </div>
                      <button
                        onClick={() =>
                          p.source === "rule"
                            ? fileRef.current?.click()
                            : setExpandedRow(expandedRow === p.id ? null : p.id)
                        }
                        className="btn btn-outline shrink-0 px-3 py-1 text-[11px]"
                      >
                        {p.source === "rule" ? "Fix in file" : "Explain"}
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              <div className="mt-4 flex items-center justify-between gap-3 border-t border-[#eee] pt-4">
                <p className="text-[11px] text-[#8a8a8a]">
                  Submitting with problems sends them to payroll for review.
                </p>
                <div className="flex shrink-0 gap-2">
                  <input
                    className="input w-56"
                    placeholder="Optional note…"
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                  />
                  <button className="btn btn-outline" disabled={uploading} onClick={submitAnyway}>
                    Submit anyway, with note
                  </button>
                  <button className="btn btn-dark" onClick={() => fileRef.current?.click()}>
                    Upload corrected file
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </Shell>
  );
}

function navItems() {
  return [
    { label: "Status", to: "/submitter/status" },
    { label: "Upload cycle", to: "/submitter/upload" },
  ];
}
