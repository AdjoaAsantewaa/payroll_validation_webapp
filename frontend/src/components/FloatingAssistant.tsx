import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useAuth } from "../context/AuthContext";

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
}

/** Pulls a route param out of the current path without relying on
 * react-router's useParams -- this widget is mounted once, globally,
 * outside any specific <Route>, so it can't use the route's own params. */
function extractIdsFromPath(pathname: string): { submissionId?: number; exceptionId?: number } {
  const exceptionsMatch = pathname.match(/^\/exceptions\/(\d+)/);
  if (exceptionsMatch) return { submissionId: Number(exceptionsMatch[1]) };
  const answerMatch = pathname.match(/^\/submitter\/answer\/(\d+)/);
  if (answerMatch) return { exceptionId: Number(answerMatch[1]) };
  return {};
}

export function FloatingAssistant() {
  const { user } = useAuth();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [prompts, setPrompts] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  // This widget is mounted once, globally, for the whole app session -- it
  // is not remounted on navigation or on login/logout. Without this, a
  // conversation started by one user (or one role) would still be sitting
  // in the panel after they log out and someone else logs in on the same
  // browser tab. Clear on every change of who's authenticated.
  useEffect(() => {
    setMessages([]);
    setPrompts([]);
    setOpen(false);
  }, [user?.email]);

  useEffect(() => {
    if (open && prompts.length === 0 && user) {
      api
        .get<{ prompts: string[] }>("/assistant/prompts")
        .then((r) => setPrompts(r.prompts))
        .catch(() => setPrompts([]));
    }
  }, [open, prompts.length, user]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, sending]);

  if (!user) return null;

  async function send(text: string) {
    const message = text.trim();
    if (!message || sending) return;
    setMessages((prev) => [...prev, { role: "user", text: message }]);
    setInput("");
    setSending(true);
    try {
      const { submissionId, exceptionId } = extractIdsFromPath(location.pathname);
      const res = await api.post<{ reply: string }>("/assistant/chat", {
        message,
        page: location.pathname,
        submission_id: submissionId,
        exception_id: exceptionId,
      });
      setMessages((prev) => [...prev, { role: "assistant", text: res.reply }]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text:
            err instanceof ApiError
              ? "I couldn't get an answer just then — try again in a moment."
              : "Something went wrong reaching the assistant.",
        },
      ]);
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      {open && (
        <div className="fixed bottom-24 right-3 z-50 flex h-[min(520px,calc(100vh-9rem))] w-[min(360px,calc(100vw-1.5rem))] flex-col overflow-hidden rounded-xl border border-[#e6e6e6] bg-white shadow-2xl sm:right-6 sm:w-[min(360px,calc(100vw-3rem))]">
          <div className="flex items-center justify-between border-b border-[#eee] bg-[#0c0d0f] px-4 py-3 text-white">
            <div className="flex items-center gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-md bg-white text-[#0c0d0f]">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none">
                  <path d="M5 13l4 4L19 7" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
              <span className="text-[13px] font-semibold">Payroll Assistant</span>
            </div>
            <button onClick={() => setOpen(false)} className="text-white/60 hover:text-white">
              ✕
            </button>
          </div>

          <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 pb-4 pt-5">
            {messages.length === 0 ? (
              <div>
                <p className="mb-3 text-[13px] text-[#555]">How can I help?</p>
                <div className="flex flex-col gap-1.5">
                  {prompts.map((p) => (
                    <button
                      key={p}
                      onClick={() => send(p)}
                      className="rounded-md border border-[#e6e6e6] px-2.5 py-1.5 text-left text-[12px] text-[#333] hover:bg-[#fafafa]"
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-2.5 pb-1">
                {messages.map((m, i) => (
                  <div
                    key={i}
                    className={`max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-[12.5px] leading-relaxed ${
                      m.role === "user"
                        ? "ml-auto bg-[#111] text-white"
                        : "mr-auto bg-[#f4f5f6] text-[#222]"
                    }`}
                  >
                    {m.text}
                  </div>
                ))}
                {sending && (
                  <div className="mr-auto rounded-lg bg-[#f4f5f6] px-3 py-2 text-[12.5px] text-[#999]">
                    Thinking…
                  </div>
                )}
              </div>
            )}
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
            className="flex gap-2 border-t border-[#eee] p-3"
          >
            <input
              className="input"
              placeholder="Ask about your current issues…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={sending}
            />
            <button type="submit" className="btn btn-dark px-3 py-2 text-[12px]" disabled={sending}>
              Send
            </button>
          </form>
        </div>
      )}

      <button
        onClick={() => setOpen((v) => !v)}
        className="fixed bottom-4 right-3 z-50 flex items-center gap-2 rounded-full bg-[#0c0d0f] px-3.5 py-2.5 text-[12.5px] font-semibold text-white shadow-lg hover:bg-[#222] sm:bottom-6 sm:right-6 sm:px-4 sm:py-3 sm:text-[13px]"
      >
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-white text-[#0c0d0f]">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none">
            <path d="M5 13l4 4L19 7" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
        Payroll Assistant
      </button>
    </>
  );
}
