"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { MessageCircle, RefreshCw, Sparkles } from "lucide-react";
import { Shell, Pill, SectionLabel } from "../components/Shell";
import {
  DeviceTile,
  SceneChip,
  StatusStat,
  sendDeviceCommand,
  type DeviceSnap,
} from "../components/DeviceTile";

const fetcher = (url: string) =>
  fetch(url).then((r) => {
    if (!r.ok) throw new Error(`${r.status}`);
    return r.json();
  });

interface Accessory {
  id: string;
  name: string;
  kind: string;
  room: string;
  reachable: boolean;
  on?: boolean | null;
  brightness?: number | null;
  temperature?: number | null;
  locked?: boolean | null;
}

interface Snapshot {
  home_id: string;
  name: string;
  accessories: Accessory[];
  captured_at: number;
}

function greeting(): string {
  const h = new Date().getHours();
  if (h < 5) return "Good night";
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

function accessoryToSnap(a: Accessory): DeviceSnap {
  return {
    id: `hk:${a.id}`,
    name: a.name,
    kind: a.kind,
    room: a.room || "Home",
    reachable: a.reachable,
    on: a.on,
    status:
      a.locked === true
        ? "Locked"
        : a.locked === false
          ? "Unlocked"
          : a.temperature != null
            ? `${a.temperature.toFixed(1)}°C`
            : undefined,
    source: "homekit",
  };
}

export default function Page() {
  const {
    data,
    error: hkError,
    isLoading,
    mutate: mutHk,
  } = useSWR<{ ok: boolean; data: Snapshot }>("/api/homekit/state", fetcher, {
    refreshInterval: 5000,
  });
  const {
    data: devData,
    error: devError,
    mutate: mutDev,
  } = useSWR<{ ok: boolean; data: DeviceSnap[] }>("/api/devices/devices", fetcher, {
    refreshInterval: 8000,
  });
  const { data: health, error: healthError } = useSWR("/api/agent/health", fetcher, {
    refreshInterval: 15000,
    shouldRetryOnError: true,
  });

  const [live, setLive] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [sceneBusy, setSceneBusy] = useState<string | null>(null);

  useEffect(() => {
    const base = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:51827";
    const url = base.includes("/ws") ? base : `${base}/ws/state`;
    let sock: WebSocket | null = null;
    try {
      sock = new WebSocket(url);
      sock.onopen = () => setLive(true);
      sock.onclose = () => setLive(false);
      sock.onerror = () => setLive(false);
    } catch {
      setLive(false);
    }
    return () => sock?.close();
  }, []);

  const snap = data?.data;
  const accessories = snap?.accessories ?? [];
  const miio = (devData?.data ?? []).map((d) => ({ ...d, source: "device" as const }));

  const all: DeviceSnap[] = useMemo(() => {
    const hk = accessories.map(accessoryToSnap);
    // Prefer miio device over HK mirror when same name/kind
    const names = new Set(miio.map((d) => d.name.toLowerCase()));
    const filteredHk = hk.filter((h) => !names.has(h.name.toLowerCase()));
    return [...miio, ...filteredHk];
  }, [accessories, miio]);

  const rooms = useMemo(() => {
    const map = new Map<string, DeviceSnap[]>();
    for (const d of all) {
      const room = d.room || "Home";
      if (!map.has(room)) map.set(room, []);
      map.get(room)!.push(d);
    }
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [all]);

  const favorites = useMemo(() => {
    // High-signal: vacuums, purifiers, anything on/cleaning, locks
    return all
      .filter(
        (d) =>
          d.kind.includes("vacuum") ||
          d.kind.includes("purifier") ||
          d.kind === "lock" ||
          d.cleaning ||
          d.on === true
      )
      .slice(0, 8);
  }, [all]);

  const vacuum = all.find((d) => d.kind.includes("vacuum"));
  const purifier = all.find((d) => d.kind.includes("purifier"));
  const lock = accessories.find((a) => a.locked != null);
  const temps = accessories.filter((a) => a.temperature != null);

  const flash = (msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(null), 2800);
  };

  const onAction = useCallback(
    async (d: DeviceSnap, action: string) => {
      if (d.source === "homekit") {
        flash("HomeKit control via bridge — use Chat or Home.app for now");
        return;
      }
      setBusyId(d.id);
      const res = await sendDeviceCommand(d.id, action);
      setBusyId(null);
      if (!res.ok) flash(res.error || "Command failed");
      else {
        flash(`${d.name}: ${action.replace("_", " ")}`);
        mutDev();
      }
    },
    [mutDev]
  );

  async function runScene(id: string) {
    setSceneBusy(id);
    try {
      if (id === "clean" && vacuum) {
        const action = vacuum.cleaning ? "stop" : "start";
        const res = await sendDeviceCommand(vacuum.id, action);
        mutDev();
        flash(
          res.ok
            ? vacuum.cleaning
              ? "Vacuum stopped"
              : "Vacuum started"
            : res.error || "Vacuum command failed"
        );
      } else if (id === "air" && purifier) {
        const action = purifier.on ? "off" : "on";
        const res = await sendDeviceCommand(purifier.id, action);
        mutDev();
        flash(
          res.ok
            ? purifier.on
              ? "Purifier off"
              : "Purifier on"
            : res.error || "Purifier command failed"
        );
      } else if (id === "away" || id === "night" || id === "home") {
        // Route through agent chat API as natural language scene
        const prompts: Record<string, string> = {
          away: "Run away scene: turn off lights, start vacuum if docked, summarize lock status",
          night: "Run night scene: lights off or dim, ensure vacuum is docked, status summary",
          home: "I'm home: stop vacuum if cleaning near doors, status summary of air and locks",
        };
        try {
          const r = await fetch("/api/agent/chat", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ user: prompts[id] }),
          });
          if (!r.ok) throw new Error(`${r.status}`);
          flash(`Scene “${id}” sent to agent`);
        } catch (e) {
          flash(`Scene “${id}” failed: ${String(e)}`);
        }
      } else {
        flash("Scene needs a linked device — add via cloud-sync");
      }
    } finally {
      setSceneBusy(null);
    }
  }

  const agentOk =
    !healthError && health != null && health.ok !== false && !health.error;

  return (
    <Shell
      title={greeting()}
      subtitle={
        <span className="flex flex-wrap items-center gap-2">
          <span>{snap?.name ?? "Home"}</span>
          <Pill ok={agentOk} label="Agent" />
          <Pill ok={!hkError && !!snap} label="HomeKit" />
          <Pill
            ok={!devError}
            label="Devices"
            detail={miio.length ? String(miio.length) : undefined}
          />
          <Pill ok={live} label={live ? "Live" : "Poll"} />
        </span>
      }
      right={
        <button
          type="button"
          onClick={() => {
            mutHk();
            mutDev();
          }}
          className="rounded-full border border-white/[0.08] bg-white/[0.03] p-2 text-fg-muted hover:bg-white/[0.06] hover:text-fg"
          aria-label="Refresh"
        >
          <RefreshCw size={16} />
        </button>
      }
    >
      {toast && (
        <div className="fixed bottom-24 left-1/2 z-50 -translate-x-1/2 rounded-full border border-white/10 bg-elevated px-4 py-2 text-sm shadow-soft sm:bottom-8">
          {toast}
        </div>
      )}

      {/* Status strip */}
      <section className="mb-6 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <StatusStat
          label="Security"
          value={
            lock
              ? lock.locked
                ? "Locked"
                : "Unlocked"
              : accessories.length
                ? "No lock"
                : "—"
          }
          tone={lock ? (lock.locked ? "ok" : "warn") : "neutral"}
        />
        <StatusStat
          label="Climate"
          value={
            temps.length
              ? `${(
                  temps.reduce((s, t) => s + (t.temperature || 0), 0) / temps.length
                ).toFixed(1)}°C`
              : "—"
          }
        />
        <StatusStat
          label="Air"
          value={
            purifier
              ? purifier.reachable
                ? purifier.aqi != null
                  ? `AQI ${purifier.aqi}`
                  : purifier.on
                    ? "On"
                    : "Off"
                : "Offline"
              : "No purifier"
          }
          tone={
            purifier && !purifier.reachable
              ? "bad"
              : purifier?.aqi != null && purifier.aqi > 100
                ? "warn"
                : purifier?.on
                  ? "ok"
                  : "neutral"
          }
        />
        <StatusStat
          label="Vacuum"
          value={
            vacuum
              ? !vacuum.reachable
                ? "Offline"
                : vacuum.cleaning
                  ? "Cleaning"
                  : vacuum.charging
                    ? "Docked"
                    : vacuum.status || "Idle"
              : "No robot"
          }
          tone={
            vacuum && !vacuum.reachable
              ? "bad"
              : vacuum?.cleaning
                ? "info"
                : vacuum?.reachable
                  ? "ok"
                  : "neutral"
          }
        />
      </section>

      {/* Scenes */}
      <section className="mb-8">
        <SectionLabel>Scenes</SectionLabel>
        <div className="flex gap-2 overflow-x-auto pb-1">
          <SceneChip
            label="Home"
            hint="Status + settle"
            active={sceneBusy === "home"}
            onClick={() => runScene("home")}
          />
          <SceneChip
            label="Away"
            hint="Secure + clean"
            active={sceneBusy === "away"}
            onClick={() => runScene("away")}
          />
          <SceneChip
            label="Clean"
            hint={vacuum?.cleaning ? "Stop vacuum" : "Start vacuum"}
            active={sceneBusy === "clean"}
            onClick={() => runScene("clean")}
          />
          <SceneChip
            label="Air"
            hint={purifier?.on ? "Purifier off" : "Purifier on"}
            active={sceneBusy === "air"}
            onClick={() => runScene("air")}
          />
          <SceneChip
            label="Night"
            hint="Wind down"
            active={sceneBusy === "night"}
            onClick={() => runScene("night")}
          />
        </div>
      </section>

      {/* Ask home */}
      <Link
        href="/chat"
        className="mb-8 flex items-center gap-3 rounded-tile border border-white/[0.08] bg-white/[0.03] px-4 py-3 transition hover:bg-white/[0.055]"
      >
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent/20 text-accent">
          <Sparkles size={16} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[14px] font-medium">Ask your home…</div>
          <div className="truncate text-[12px] text-fg-faint">
            “Is the Dreame docked?” · “Turn on the purifier”
          </div>
        </div>
        <MessageCircle size={16} className="text-fg-faint" />
      </Link>

      {/* Errors / empty */}
      {hkError && devError && (
        <div className="mb-6 rounded-tile border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-fg-secondary">
          Agent services offline. Start with{" "}
          <code className="rounded bg-white/10 px-1 text-xs">make run</code> or check
          ports 8000 / 51827 / 8002.
        </div>
      )}

      {isLoading && all.length === 0 && (
        <p className="text-sm text-fg-muted">Loading home…</p>
      )}

      {all.length === 0 && !isLoading && (
        <div className="mb-8 rounded-tile border border-white/[0.08] bg-white/[0.03] p-6">
          <h3 className="text-lg font-medium">No devices yet</h3>
          <p className="mt-2 max-w-md text-sm text-fg-muted">
            Pair HomeKit bridge accessories, or pull Xiaomi / Dreame tokens:
          </p>
          <pre className="mt-3 overflow-x-auto rounded-lg bg-black/40 p-3 text-[12px] text-fg-secondary">
            {`homepod-agent devices cloud-sync \\
  --username YOU --password '…' --country de`}
          </pre>
          <p className="mt-3 text-xs text-fg-faint">
            See docs/devices.md · Dreame found on LAN needs cloud token once.
          </p>
        </div>
      )}

      {/* Favorites */}
      {favorites.length > 0 && (
        <section className="mb-8">
          <SectionLabel>Favorites</SectionLabel>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {favorites.map((d) => (
              <DeviceTile
                key={d.id}
                d={d}
                busy={busyId === d.id}
                onAction={onAction}
              />
            ))}
          </div>
        </section>
      )}

      {/* Rooms */}
      {rooms.map(([room, devices]) => (
        <section key={room} className="mb-8">
          <SectionLabel>{room}</SectionLabel>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {devices.map((d) => (
              <DeviceTile
                key={d.id}
                d={d}
                busy={busyId === d.id}
                onAction={onAction}
              />
            ))}
          </div>
        </section>
      ))}

      {/* Automation teaser */}
      <section className="mb-4 rounded-tile border border-dashed border-white/[0.1] bg-white/[0.02] p-4">
        <SectionLabel>Suggested automations</SectionLabel>
        <ul className="space-y-2 text-sm text-fg-secondary">
          <li className="flex gap-2">
            <span className="text-accent">→</span>
            Away: start vacuum when last phone leaves Wi‑Fi
          </li>
          <li className="flex gap-2">
            <span className="text-accent">→</span>
            Air: purifier on when AQI &gt; 100
          </li>
          <li className="flex gap-2">
            <span className="text-accent">→</span>
            Night: dock vacuum + summary via agent
          </li>
        </ul>
        <p className="mt-3 text-xs text-fg-faint">
          Spec in docs/ux-home-experience.md — wire rules after tokens land.
        </p>
      </section>
    </Shell>
  );
}
