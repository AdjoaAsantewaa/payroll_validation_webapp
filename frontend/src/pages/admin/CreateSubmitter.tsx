import { useEffect, useState } from "react";
import { Shell } from "../../components/Shell";
import { api, ApiError } from "../../api/client";
import type { Department, Submitter, CreateSubmitterResult } from "../../types";

export default function CreateSubmitter() {
  const [departments, setDepartments] = useState<Department[]>([]);
  const [submitters, setSubmitters] = useState<Submitter[]>([]);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [departmentId, setDepartmentId] = useState<number | "">("");
  const [error, setError] = useState<string | null>(null);
  const [credentials, setCredentials] = useState<CreateSubmitterResult | null>(null);
  const [copied, setCopied] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function load() {
    const [depts, subs] = await Promise.all([
      api.get<Department[]>("/admin/departments"),
      api.get<Submitter[]>("/admin/submitters"),
    ]);
    setDepartments(depts);
    setSubmitters(subs);
  }

  useEffect(() => {
    load();
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    // A fresh attempt retires the previous one-time credentials immediately
    // — they're shown once, not kept around while a new submitter is created.
    setCredentials(null);
    setCopied(false);
    if (departmentId === "") {
      setError("Choose a department.");
      return;
    }
    setSubmitting(true);
    try {
      const res = await api.post<CreateSubmitterResult>("/admin/submitters", {
        name: name.trim(),
        email: email.trim(),
        department_id: departmentId,
      });
      setCredentials(res);
      setName("");
      setEmail("");
      setDepartmentId("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setSubmitting(false);
    }
  }

  async function copyCredentials() {
    if (!credentials) return;
    const text = `Email: ${credentials.email}\nTemporary password: ${credentials.temporary_password}`;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API can be unavailable (e.g. non-HTTPS context); the
      // credentials are still visible on screen to copy by hand.
    }
  }

  return (
    <Shell title="Create submitter" navItems={navItems()}>
      <div className="mb-6">
        <h1 className="text-[22px] font-bold tracking-tight">Create submitter</h1>
        <p className="mt-1 text-[13px] text-[#8a8a8a]">
          Add a submitter's name, email, and department. A temporary password is generated and
          shown once below — copy it to share with them. Email delivery is best-effort and
          optional; account creation and login don't depend on it.
        </p>
      </div>

      {credentials && (
        <div className="mb-6 rounded-lg border border-[#f6dfae] bg-[#fdf7ec] px-5 py-4">
          <div className="mb-2 flex items-center justify-between">
            <div className="text-[13px] font-semibold text-[#8a6416]">
              Submitter created — shown once
            </div>
            <div className="text-[11px] text-[#8a6416]">
              {credentials.email_sent
                ? "Also emailed to the submitter."
                : "Not emailed — copy and share this manually."}
            </div>
          </div>
          <p className="mb-3 text-[12px] text-[#8a6416]">
            This password cannot be shown again after you leave this page. Copy it now.
          </p>
          <div className="mb-3 flex flex-col gap-1.5 rounded-md border border-[#f0dca0] bg-white px-3 py-2.5 font-mono text-[12.5px]">
            <div>
              <span className="text-[#8a8a8a]">Email: </span>
              <span className="font-semibold text-[#111]">{credentials.email}</span>
            </div>
            <div>
              <span className="text-[#8a8a8a]">Temporary password: </span>
              <span className="font-semibold text-[#111]">{credentials.temporary_password}</span>
            </div>
          </div>
          <button onClick={copyCredentials} className="btn btn-dark px-3 py-1.5 text-[11px]">
            {copied ? "Copied ✓" : "Copy credentials"}
          </button>
        </div>
      )}

      <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-[380px_1fr]">
        <form onSubmit={handleSubmit} className="card flex flex-col gap-4 px-5 py-5">
          <div>
            <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-[#8a8a8a]">
              Full name
            </label>
            <input
              className="input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-[#8a8a8a]">
              Work email
            </label>
            <input
              className="input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-[#8a8a8a]">
              Department
            </label>
            <select
              className="input"
              value={departmentId}
              onChange={(e) => setDepartmentId(e.target.value ? Number(e.target.value) : "")}
              required
            >
              <option value="">Select a department…</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </div>

          {error && (
            <div className="rounded-md bg-[#fdecec] px-3 py-2 text-[12px] text-[#b91c1c]">
              {error}
            </div>
          )}

          <button type="submit" className="btn btn-dark w-full py-2.5" disabled={submitting}>
            {submitting ? "Creating…" : "Create submitter"}
          </button>
        </form>

        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="table-clean">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Department</th>
                </tr>
              </thead>
              <tbody>
                {submitters.map((s) => (
                  <tr key={s.id}>
                    <td className="font-medium">{s.name}</td>
                    <td className="text-[#8a8a8a]">{s.email}</td>
                    <td>{s.department || "—"}</td>
                  </tr>
                ))}
                {submitters.length === 0 && (
                  <tr>
                    <td colSpan={3} className="text-[#8a8a8a]">
                      No submitters created yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </Shell>
  );
}

function navItems() {
  return [{ label: "Create submitter", to: "/admin" }];
}
