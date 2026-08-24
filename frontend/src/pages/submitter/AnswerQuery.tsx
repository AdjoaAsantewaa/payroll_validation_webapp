import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Shell } from "../../components/Shell";
import { api, ApiError } from "../../api/client";
import type { ExceptionItem } from "../../types";

interface StatusResponse {
  open_questions: ExceptionItem[];
}

type AnswerType = "correct" | "wrong" | "not_sure";

export default function AnswerQuery() {
  const { exceptionId } = useParams();
  const navigate = useNavigate();
  const [question, setQuestion] = useState<ExceptionItem | null>(null);
  const [answer, setAnswer] = useState<AnswerType | null>(null);
  const [note, setNote] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<StatusResponse>("/submissions/status").then((d) => {
      const q = d.open_questions.find((x) => x.id === Number(exceptionId));
      setQuestion(q || null);
    });
  }, [exceptionId]);

  async function send() {
    if (!question || !answer) return;
    setSending(true);
    setError(null);
    try {
      await api.post(`/exceptions/${question.id}/answer`, { answer_type: answer, note });
      navigate("/submitter/status");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setSending(false);
    }
  }

  return (
    <Shell breadcrumb="Status" title="Answer query" navItems={navItems()}>
      <button
        onClick={() => navigate("/submitter/status")}
        className="mb-3 text-[12px] text-[#8a8a8a] hover:text-[#111]"
      >
        ← Status
      </button>

      {!question ? (
        <div className="text-[13px] text-[#8a8a8a]">
          This question is no longer open — it may already have been answered.
        </div>
      ) : (
        <div className="max-w-[560px] card p-5">
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-[#8a8a8a]">
            Question from payroll
          </div>
          <h1 className="mb-3 text-[16px] font-bold">{question.row_label}</h1>
          <p className="mb-4 text-[13px] leading-relaxed text-[#333]">{question.issue_text}</p>

          {(question.submitted_value || question.usual_value) && (
            <table className="table-clean mb-4">
              <thead>
                <tr>
                  <th>Field</th>
                  <th>You sent</th>
                  <th>Usual</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>{question.field}</td>
                  <td className="font-semibold">{question.submitted_value ?? "—"}</td>
                  <td className="text-[#8a8a8a]">{question.usual_value ?? "—"}</td>
                </tr>
              </tbody>
            </table>
          )}

          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[#8a8a8a]">
            Your answer
          </div>
          <div className="mb-3 flex gap-2">
            {(
              [
                { key: "correct", label: "The value is correct" },
                { key: "wrong", label: "It's wrong — I'll resubmit" },
                { key: "not_sure", label: "Not sure" },
              ] as { key: AnswerType; label: string }[]
            ).map((opt) => (
              <button
                key={opt.key}
                onClick={() => setAnswer(opt.key)}
                className={`rounded-full border px-3 py-1.5 text-[11.5px] font-medium ${
                  answer === opt.key
                    ? "border-[#111] bg-[#111] text-white"
                    : "border-[#d8d8d8] bg-white text-[#333]"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>

          <textarea
            className="input mb-4"
            rows={3}
            placeholder="Explain briefly — e.g. 'covered two absent staff over the bank holiday'…"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />

          {error && (
            <div className="mb-3 rounded-md bg-[#fdecec] px-3 py-2 text-[12px] text-[#b91c1c]">{error}</div>
          )}

          <div className="flex gap-2">
            <button
              className="btn btn-outline flex-1"
              onClick={() => navigate("/submitter/upload")}
            >
              Upload corrected file instead
            </button>
            <button className="btn btn-dark flex-1" disabled={!answer || sending} onClick={send}>
              {sending ? "Sending…" : "Send answer"}
            </button>
          </div>

          <p className="mt-3 text-[10px] text-[#999]">
            The answer lands on the exception itself, so it's in the audit trail — not in someone's
            mailbox.
          </p>
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
