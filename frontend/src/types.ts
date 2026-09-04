export type Role = "specialist" | "submitter" | "admin";

export interface AuthUser {
  access_token: string;
  role: Role;
  name: string;
  initials: string;
  email: string;
  department?: string | null;
  department_id?: number | null;
}

export function homeForRole(role: Role): string {
  if (role === "specialist") return "/dashboard";
  if (role === "admin") return "/admin";
  return "/submitter/status";
}

export interface Department {
  id: number;
  name: string;
}

export interface Submitter {
  id: number;
  name: string;
  email: string;
  department?: string | null;
  department_id?: number | null;
}

/** Only ever present on the create-submitter response, once, right after
 * creation — never returned by GET /admin/submitters and never stored
 * client-side beyond this session's in-memory state. */
export interface CreateSubmitterResult extends Submitter {
  temporary_password: string;
  email_sent: boolean;
}

export interface DashboardData {
  cycle: { id: number; label: string; cutoff_date: string };
  pipeline: {
    submitted: number;
    mapped: number;
    validated: number;
    resolve: number;
    approve: number;
    export: number;
    total_departments: number;
  };
  stats: {
    needs_you: number;
    submitted_of_total: string;
    not_in_yet: number;
    self_fixed: number;
    approved: number;
  };
  chart: { department: string; count: number }[];
  departments: DepartmentRow[];
}

export interface DepartmentRow {
  submission_id: number;
  department: string;
  department_id: number;
  status: "not_submitted" | "needs_review" | "query_sent" | "approved";
  rows: number;
  exceptions: number;
  exceptions_high: number;
  last_activity: string | null;
}

export interface ExceptionItem {
  id: number;
  row_label: string;
  field: string | null;
  severity: "high" | "med" | "low";
  /** Internal only -- kept for debugging/audit, never rendered. Use
   * issue_type for anything shown to a user. */
  source: "rule" | "ai";
  issue_text: string;
  submitted_value: string | null;
  usual_value: string | null;
  ai_explanation: string | null;
  recommended_action: string | null;
  status: "open" | "accepted" | "rejected" | "query_open" | "query_answered";
  note: string | null;
  /** Plain-language category, e.g. "Exited employee", "Unusual overtime". */
  issue_type: string;
  /** What's wrong, in plain language -- pair with recommended_action. */
  problem: string;
  row?: {
    staff_id: string | null;
    full_name: string | null;
    overtime_hours: number | null;
    basic_pay: number | null;
    allowances: number | null;
  } | null;
}

export interface SubmissionDetail {
  id: number;
  department: string;
  department_id: number;
  cycle: string;
  version: number;
  is_current: boolean;
  status: string;
  row_count: number;
  self_fixed_count: number;
  filename: string | null;
  submitted_by: string | null;
  uploaded_at: string | null;
  approved_at: string | null;
  approved_by: string | null;
  superseded_at: string | null;
  exceptions: ExceptionItem[];
  queries: { subject: string; status: string; sent_at: string | null; to_emails: string | null }[];
  file_retained: boolean;
}
