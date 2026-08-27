import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import { StatusBadge, SeverityBadge, SourceBadge } from "./StatusBadge";
import type { SubmissionDetail } from "../types";

export function SubmissionDetailModal({
  submissionId,
  onClose,
}: {
  submissionId: number;
  onClose: () => void;
}) {
  const [data, setData] = useState<SubmissionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get<SubmissionDetail>(`/submissions/${submissionId}`)
      .then((d) => !cancelled && setData(d))
      .catch((err) =>
        !cancelled &&
        setError(err instanceof ApiError ? err.message : "Could not load this submission")
      );
    return () => {
      cancelled = true;
    };
  }, [submissionId]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      onClick={onClose}
    >
      <div
        className="max-h-[85vh] w-full max-w-[640px] overflow-y-auto rounded-xl bg-white p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {error && <div className="text-[13px] text-[#b91c1c]">{error}</div>}

        {!data && !error && <div className="text-[13px] text-[#8a8a8a]">Loading…</div>}

        {data && (
          <>
            <div className="mb-4 flex items-start justify-between">
              <div>
                <h2 className="text-[16px] font-bold">
                  {data.department} · {data.cycle}
                </h2>
                <p className="mt-0.5 text-[12px] text-[#8a8a8a]">
                  Version {data.version}
                  {!data.is_current && " · superseded"} · {data.row_count} rows
                </p>
              </div>
              <button onClick={onClose} className="text-[#8a8a8a] hover:text-[#111]">
                ✕
              </button>
            </div>

            <div className="mb-4 grid grid-cols-2 gap-3 text-[12px]">
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-wide text-[#8a8a8a]">
                  Status
                </div>
                <StatusBadge status={data.status} />
              </div>
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-wide text-[#8a8a8a]">
                  Self-fixed
                </div>
                {data.self_fixed_count}
              </div>
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-wide text-[#8a8a8a]">
                  Submitted by
                </div>
                {data.submitted_by || "—"}
              </div>
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-wide text-[#8a8a8a]">
                  Uploaded
                </div>
                {formatDate(data.uploaded_at)}
              </div>
              {data.approved_at && (
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-[#8a8a8a]">
                    Approved
                  </div>
                  {formatDate(data.approved_at)} by {data.approved_by}
                </div>
              )}
              {data.superseded_at && (
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-[#8a8a8a]">
                    Superseded
                  </div>
                  {formatDate(data.superseded_at)}
                </div>
              )}
            </div>

            {!data.file_retained && (
              <div className="mb-4 rounded-md bg-[#f6f6f6] px-3 py-2 text-[11px] text-[#666]">
                The original file isn't stored — this is the parsed submission record (rows,
                validation results, queries, and outcome).
              </div>
            )}

            <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[#8a8a8a]">
              Validation results ({data.exceptions.length})
            </div>
            {data.exceptions.length === 0 ? (
              <div className="mb-4 text-[12px] text-[#8a8a8a]">No exceptions — clean submission.</div>
            ) : (
              <div className="mb-4 flex flex-col gap-1.5">
                {data.exceptions.map((e) => (
                  <div key={e.id} className="rounded-md border border-[#eee] px-2.5 py-2 text-[12px]">
                    <div className="mb-1 flex items-center gap-1.5">
                      <SeverityBadge severity={e.severity} />
                      <SourceBadge source={e.source} />
                      <span className="font-semibold">{e.row_label}</span>
                      <StatusBadge status={e.status} />
                    </div>
                    <div className="text-[#555]">{e.issue_text}</div>
                  </div>
                ))}
              </div>
            )}

            {data.queries.length > 0 && (
              <>
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[#8a8a8a]">
                  Correction requests sent
                </div>
                <div className="flex flex-col gap-1.5">
                  {data.queries.map((q, i) => (
                    <div key={i} className="rounded-md border border-[#eee] px-2.5 py-2 text-[12px]">
                      <div className="font-semibold">{q.subject}</div>
                      <div className="text-[#8a8a8a]">
                        {q.to_emails} · {formatDate(q.sent_at)} · {q.status}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}
