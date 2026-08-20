"use client";

import { useEffect, useState } from "react";
import { Shell, SectionLabel } from "../../components/Shell";

interface Settings {
  ok?: boolean;
  llm?: { local: string; hosted: string; prefer_local: string };
  memory_facts?: number;
  error?: string;
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pods, setPods] = useState<
    Array<{ name: string; address: string; room: string | null }>
  >([]);
  const [devHealth, setDevHealth] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    fetch("/api/agent/health")
      .then((r) => r.json())
      .then((d) => setSettings(d))
      .catch((e) => setError(String(e)));
    fetch("/api/agent/pods")
      .then((r) => r.json())
      .then((d) => setPods(d.data ?? []))
      .catch(() => setPods([]));
    fetch("/api/devices/health")
      .then((r) => r.json())
      .then((d) => setDevHealth(d))
      .catch(() => setDevHealth(null));
  }, []);

  return (
    <Shell title="Settings" subtitle="Local services & paths">
      <section className="mb-6 rounded-tile border border-white/[0.08] bg-white/[0.03] p-4">
        <SectionLabel>LLM router</SectionLabel>
        {settings?.llm ? (
          <dl className="space-y-2 text-sm">
            <Row label="Local model" value={settings.llm.local} />
            <Row label="Hosted model" value={settings.llm.hosted} />
            <Row label="Prefer local" value={settings.llm.prefer_local} />
            <Row label="Memory facts" value={String(settings.memory_facts ?? 0)} />
          </dl>
        ) : error ? (
          <p className="text-sm text-danger">{error}</p>
        ) : (
          <p className="text-sm text-fg-muted">Loading…</p>
        )}
      </section>

      <section className="mb-6 rounded-tile border border-white/[0.08] bg-white/[0.03] p-4">
        <SectionLabel>Devices service</SectionLabel>
        {devHealth ? (
          <dl className="space-y-2 text-sm">
            <Row label="OK" value={String(devHealth.ok)} />
            <Row label="Devices" value={String(devHealth.device_count ?? "—")} />
            <Row label="Reachable" value={String(devHealth.reachable ?? "—")} />
          </dl>
        ) : (
          <p className="text-sm text-fg-muted">
            Not reachable on :8002 — start{" "}
            <code className="rounded bg-white/10 px-1 text-xs">devices serve</code>
          </p>
        )}
        <p className="mt-3 text-xs text-fg-faint">
          Tokens live in ~/.homepod-agent/devices.yaml (never commit). Cloud-sync needs Xiaomi
          2FA when rate-limit allows.
        </p>
      </section>

      <section className="mb-6 rounded-tile border border-white/[0.08] bg-white/[0.03] p-4">
        <SectionLabel>HomePods on LAN</SectionLabel>
        {pods.length === 0 ? (
          <p className="text-sm text-fg-muted">None discovered (or agent offline).</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {pods.map((p, i) => (
              <li
                key={i}
                className="flex items-center justify-between gap-3 border-b border-white/[0.05] py-2 last:border-0"
              >
                <span className="font-medium">{p.name}</span>
                <span className="font-mono text-xs text-fg-faint">
                  {p.address}
                  {p.room && ` · ${p.room}`}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mb-6 rounded-tile border border-white/[0.08] bg-white/[0.03] p-4">
        <SectionLabel>iPad voice</SectionLabel>
        <p className="text-sm text-fg-muted">
          Install <code className="rounded bg-white/10 px-1 text-xs">ipad-listen/</code> and set
          WebSocket to{" "}
          <code className="rounded bg-white/10 px-1 text-xs">ws://&lt;mac-ip&gt;:8000/ws/voice</code>
          .
        </p>
      </section>

      <section className="mb-6 rounded-tile border border-white/[0.08] bg-white/[0.03] p-4">
        <SectionLabel>State directory</SectionLabel>
        <p className="text-sm text-fg-muted">
          Pairing, memory DB, devices.yaml, logs:{" "}
          <code className="rounded bg-white/10 px-1 text-xs">~/.homepod-agent/</code>
        </p>
      </section>

      <section className="rounded-tile border border-dashed border-white/[0.1] p-4">
        <SectionLabel>UX principles</SectionLabel>
        <p className="text-sm text-fg-muted">
          Full research + automation roadmap:{" "}
          <code className="rounded bg-white/10 px-1 text-xs">docs/ux-home-experience.md</code>
        </p>
      </section>
    </Shell>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="text-fg-muted">{label}</dt>
      <dd className="truncate font-mono text-[13px] text-fg-secondary">{value}</dd>
    </div>
  );
}
