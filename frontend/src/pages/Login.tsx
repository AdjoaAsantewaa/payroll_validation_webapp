import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../api/client";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("k.owusu@company.com");
  const [password, setPassword] = useState("password123");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const user = await login(email, password);
      navigate(user.role === "specialist" ? "/dashboard" : "/submitter/status");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setSubmitting(false);
    }
  }

  function quickFill(role: "specialist" | "submitter") {
    if (role === "specialist") {
      setEmail("k.owusu@company.com");
    } else {
      setEmail("a.mensah@company.com");
    }
    setPassword("password123");
  }

  return (
    <div className="flex h-screen items-center justify-center bg-[#0c0d0f] px-4">
      <div className="w-full max-w-[380px] rounded-2xl bg-white p-8 shadow-2xl">
        <div className="mb-6 flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#0c0d0f] text-white">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
              <path d="M5 13l4 4L19 7" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div>
            <div className="text-[15px] font-bold leading-tight">Payroll Validation</div>
            <div className="text-[12px] text-[#8a8a8a]">Sign in to continue</div>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
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
              Password
            </label>
            <input
              className="input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          {error && (
            <div className="rounded-md bg-[#fdecec] px-3 py-2 text-[12px] text-[#b91c1c]">
              {error}
            </div>
          )}

          <button type="submit" className="btn btn-dark w-full py-2.5" disabled={submitting}>
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <div className="mt-5 rounded-md border border-dashed border-[#d8d8d8] bg-[#fafafa] p-3 text-[11px] leading-relaxed text-[#666]">
          <span className="font-semibold text-[#333]">No role picker.</span> Auth returns the role
          automatically — specialists land on the Dashboard, submitters land on Upload. For this
          demo, choose a role to preview:
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              onClick={() => quickFill("specialist")}
              className="btn btn-outline flex-1 py-1.5 text-[11px]"
            >
              Specialist
            </button>
            <button
              type="button"
              onClick={() => quickFill("submitter")}
              className="btn btn-outline flex-1 py-1.5 text-[11px]"
            >
              Submitter
            </button>
          </div>
          <div className="mt-2 text-[10px] text-[#999]">Demo password: password123</div>
        </div>
      </div>
    </div>
  );
}
