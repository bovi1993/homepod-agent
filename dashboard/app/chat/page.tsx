"use client";

import { useEffect, useRef, useState } from "react";

interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  route?: string;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [ws, setWs] = useState<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const url = (process.env.NEXT_PUBLIC_AGENT_WS_URL ?? "ws://localhost:8000") + "/ws/chat";
    const sock = new WebSocket(url);
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
        }
      } catch {
        /* ignore */
      }
    };
    setWs(sock);
    return () => sock.close();
  }, []);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [messages]);

  async function send(text: string) {
    if (!text.trim()) return;
    const userMsg: Message = { id: crypto.randomUUID(), role: "user", content: text };
    setMessages((m) => [...m, userMsg]);
    setInput("");

    // Try WebSocket first if available, fall back to HTTP POST
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ user: text }));
    } else {
      try {
        const r = await fetch("/api/agent/chat", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ user: text }),
        });
        const data = await r.json();
        const reply = data?.data?.reply ?? "(no reply)";
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
          {
            id: crypto.randomUUID(),
            role: "system",
            content: `Error: ${String(e)}`,
          },
        ]);
      }
    }
  }

  return (
    <main className="mx-auto flex h-screen max-w-3xl flex-col px-6 py-8">
      <header className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Chat</h1>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span
            className={`h-2 w-2 rounded-full ${connected ? "bg-green-500" : "bg-gray-400"}`}
          />
          {connected ? "live" : "polling (HTTP)"}
        </div>
      </header>

      <div ref={logRef} className="flex-1 overflow-y-auto rounded-md border border-border bg-card p-4">
        {messages.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Try: "turn on the bedroom light" or "is the front door locked?"
          </p>
        )}
        <div className="space-y-4">
          {messages.map((m) => (
            <div
              key={m.id}
              className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] rounded-lg px-4 py-2 text-sm ${
                  m.role === "user"
                    ? "bg-accent text-white"
                    : m.role === "system"
                    ? "bg-red-50 text-red-800"
                    : "bg-border text-foreground"
                }`}
              >
                <div>{m.content}</div>
                {m.route && (
                  <div className="mt-1 text-[10px] uppercase tracking-wide opacity-70">
                    {m.route}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="mt-4 flex gap-2"
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Say something to your home…"
          className="flex-1 rounded-md border border-border bg-card px-4 py-2 text-sm focus:border-accent focus:outline-none"
        />
        <button
          type="submit"
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90"
        >
          Send
        </button>
      </form>
    </main>
  );
}