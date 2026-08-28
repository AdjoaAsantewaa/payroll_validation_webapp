import { useEffect, useState } from "react";
import { Shell } from "../../components/Shell";
import { api, ApiError } from "../../api/client";
import type { Department, Submitter } from "../../types";

export default function CreateSubmitter() {
  const [departments, setDepartments] = useState<Department[]>([]);
  const [submitters, setSubmitters] = useState<Submitter[]>([]);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [departmentId, setDepartmentId] = useState<number | "">("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
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
    setSuccess(null);
    if (departmentId === "") {
      setError("Choose a department.");
      return;
    }
    setSubmitting(true);
    try {
      await api.post<Submitter>("/admin/submitters", {
        name: name.trim(),
        email: email.trim(),
        department_id: departmentId,
      });
      setSuccess(`Credentials sent to ${email.trim()}.`);
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

  return (
    <Shell title="Create submitter" navItems={navItems()}>
      <div className="mb-6">
        <h1 className="text-[22px] font-bold tracking-tight">Create submitter</h1>
        <p className="mt-1 text-[13px] text-[#8a8a8a]">
          Add a submitter's name, email, and department — a password is generated and the
          login details are emailed to them automatically.
        </p>
      </div>

      <div className="mb-6 grid grid-cols-[380px_1fr] gap-6">
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
          {success && (
            <div className="rounded-md bg-[#eafaf0] px-3 py-2 text-[12px] text-[#1e7e42]">
              {success}
            </div>
          )}

          <button type="submit" className="btn btn-dark w-full py-2.5" disabled={submitting}>
            {submitting ? "Creating…" : "Create & send credentials"}
          </button>
        </form>

        <div className="card overflow-hidden">
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
    </Shell>
  );
}

function navItems() {
  return [{ label: "Create submitter", to: "/admin" }];
}
