"use client";

import { useEffect, useState } from "react";

interface Settings {
  llm: { local: string; hosted: string; prefer_local: string };
  memory_facts: number;
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pods, setPods] = useState<
    Array<{ name: string; address: string; room: string | null }>
  >([]);

  useEffect(() => {
    fetch("/api/agent/health")
      .then((r) => r.json())
      .then((d) => setSettings(d))
      .catch((e) => setError(String(e)));
    fetch("/api/agent/pods")
      .then((r) => r.json())
      .then((d) => setPods(d.data ?? []))
      .catch(() => setPods([]));
  }, []);

  return (
    <main className="mx-auto max-w-3xl px-6 py-8">
      <h1 className="mb-6 text-3xl font-semibold">Settings</h1>

      <section className="mb-8 rounded-lg border border-border bg-card p-4">
        <h2 className="mb-2 text-lg font-medium">LLM Router</h2>
        {settings?.llm ? (
          <dl className="space-y-2 text-sm">
            <Row label="Local model" value={settings.llm.local} />
            <Row label="Hosted model" value={settings.llm.hosted} />
            <Row label="Prefer local" value={settings.llm.prefer_local} />
            <Row label="Memory facts" value={String(settings.memory_facts)} />
          </dl>
        ) : error ? (
          <p className="text-red-700">{error}</p>
        ) : (
          <p className="text-muted-foreground">Loading…</p>
        )}
      </section>

      <section className="mb-8 rounded-lg border border-border bg-card p-4">
        <h2 className="mb-2 text-lg font-medium">Discovered HomePods</h2>
        {pods.length === 0 ? (
          <p className="text-muted-foreground">No HomePods on the LAN.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {pods.map((p, i) => (
              <li key={i} className="flex items-center justify-between">
                <span>{p.name}</span>
                <span className="font-mono text-xs text-muted-foreground">
                  {p.address}
                  {p.room && ` · ${p.room}`}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mb-8 rounded-lg border border-border bg-card p-4">
        <h2 className="mb-2 text-lg font-medium">iPad Voice Client</h2>
        <p className="text-sm text-muted-foreground">
          Build and install <code className="rounded bg-border px-1 py-0.5 text-xs">ipad-listen/</code>{" "}
          to your iPad. Set the WebSocket URL to{" "}
          <code className="rounded bg-border px-1 py-0.5 text-xs">
            ws://&lt;mac-ip&gt;:8000/ws/voice
          </code>
          .
        </p>
      </section>

      <section className="mb-8 rounded-lg border border-border bg-card p-4">
        <h2 className="mb-2 text-lg font-medium">State directory</h2>
        <p className="text-sm text-muted-foreground">
          Pairing config, memory DB, and logs live at{" "}
          <code className="rounded bg-border px-1 py-0.5 text-xs">~/.homepod-agent/</code>.
        </p>
      </section>
    </main>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-mono">{value}</dd>
    </div>
  );
}