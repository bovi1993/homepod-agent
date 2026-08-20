"use client";

import { useEffect, useRef, useState } from "react";
import { Shell, Pill } from "../../components/Shell";

interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  route?: string;
}

const SUGGESTIONS = [
  "Is the Dreame docked?",
  "Turn on the air purifier",
  "What’s the home status?",
  "Start cleaning the house",
];

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [ws, setWs] = useState<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [sending, setSending] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const base = process.env.NEXT_PUBLIC_AGENT_WS_URL ?? "ws://localhost:8000";
    const url = base.includes("/ws") ? base : `${base}/ws/chat`;
    let sock: WebSocket | null = null;
    try {
      sock = new WebSocket(url);
      sock.onopen = () => setConnected(true);
      sock.onclose = () => setConnected(false);
      sock.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          if (data.type === "reply" && data.payload) {
            setMessages((m) => [
              ...m,
              {
                id: crypto.randomUUID(),
                role: "assistant",
                content: data.payload.reply,
                route: data.payload.route,
              },
            ]);
            setSending(false);
          }
        } catch {
          /* ignore */
        }
      };
      setWs(sock);
    } catch {
      setConnected(false);
    }
    return () => sock?.close();
  }, []);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function send(text: string) {
    if (!text.trim() || sending) return;
    const userMsg: Message = { id: crypto.randomUUID(), role: "user", content: text };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setSending(true);

    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ user: text }));
      // sending cleared on reply; timeout fallback
      window.setTimeout(() => setSending(false), 45000);
    } else {
      try {
        const r = await fetch("/api/agent/chat", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ user: text }),
        });
        const data = await r.json();
        const reply = data?.data?.reply ?? data?.reply ?? "(no reply)";
        setMessages((m) => [
          ...m,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            content: reply,
            route: data?.data?.route,
          },
        ]);
      } catch (e) {
        setMessages((m) => [
          ...m,
          { id: crypto.randomUUID(), role: "system", content: `Error: ${String(e)}` },
        ]);
      } finally {
        setSending(false);
      }
    }
  }

  return (
    <Shell
      title="Chat"
      subtitle={<Pill ok={connected} label={connected ? "Live socket" : "HTTP fallback"} />}
    >
      <div className="flex h-[calc(100dvh-11rem)] flex-col sm:h-[calc(100dvh-9rem)]">
        <div
          ref={logRef}
          className="flex-1 space-y-3 overflow-y-auto rounded-tile border border-white/[0.08] bg-white/[0.02] p-4"
        >
          {messages.length === 0 && (
            <div>
              <p className="text-sm text-fg-muted">
                Natural language control — routes through local tools when possible.
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => send(s)}
                    className="rounded-chip border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-[13px] text-fg-secondary hover:bg-white/[0.06]"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m) => (
            <div
              key={m.id}
              className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-[14px] leading-relaxed ${
                  m.role === "user"
                    ? "bg-accent text-white"
                    : m.role === "system"
                      ? "border border-danger/30 bg-danger/10 text-fg-secondary"
                      : "border border-white/[0.08] bg-white/[0.05] text-fg"
                }`}
              >
                <div className="whitespace-pre-wrap">{m.content}</div>
                {m.route && (
                  <div className="mt-1 text-[10px] uppercase tracking-wide text-fg-faint">
                    {m.route}
                  </div>
                )}
              </div>
            </div>
          ))}
          {sending && (
            <div className="text-[12px] text-fg-faint">Home is thinking…</div>
          )}
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
          className="mt-3 flex gap-2"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Message your home…"
            className="flex-1 rounded-tile border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-sm text-fg placeholder:text-fg-faint focus:border-accent/50 focus:outline-none"
          />
          <button
            type="submit"
            disabled={sending}
            className="rounded-tile bg-accent px-5 py-3 text-sm font-medium text-white hover:bg-accent-deep disabled:opacity-50"
          >
            Send
          </button>
        </form>
      </div>
    </Shell>
  );
}
