const STATUS_MAP: Record<string, { label: string; cls: string }> = {
  not_submitted: { label: "Not submitted", cls: "badge-grey" },
  needs_review: { label: "Needs review", cls: "badge-red" },
  query_sent: { label: "Query sent", cls: "badge-amber" },
  approved: { label: "Approved", cls: "badge-green" },
  open: { label: "Open", cls: "badge-red" },
  accepted: { label: "Accepted", cls: "badge-green" },
  rejected: { label: "Rejected", cls: "badge-grey" },
  query_open: { label: "Query open", cls: "badge-amber" },
  query_answered: { label: "Answered", cls: "badge-blue" },
};

export function StatusBadge({ status }: { status: string }) {
  const meta = STATUS_MAP[status] || { label: status, cls: "badge-grey" };
  return <span className={`badge ${meta.cls}`}>{meta.label}</span>;
}

const SEVERITY_MAP: Record<string, string> = {
  high: "badge-red",
  med: "badge-amber",
  low: "badge-grey",
};

export function SeverityBadge({ severity }: { severity: string }) {
  return <span className={`badge ${SEVERITY_MAP[severity] || "badge-grey"}`}>{severity}</span>;
}

/** Plain-language issue category shown to users -- e.g. "Exited employee",
 * "Unusual overtime". Deliberately does not reveal whether the issue came
 * from deterministic validation or contextual judgement; see
 * backend/app/issue_presentation.py. */
export function IssueTypeBadge({ issueType }: { issueType: string }) {
  return <span className="badge badge-grey">{issueType}</span>;
}
