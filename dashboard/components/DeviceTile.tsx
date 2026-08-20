"use client";

import { clsx } from "clsx";
import {
  Battery,
  Disc3,
  Fan,
  Lightbulb,
  Lock,
  Power,
  Thermometer,
  Wind,
  type LucideIcon,
} from "lucide-react";

export type DeviceSnap = {
  id: string;
  name: string;
  kind: string;
  room: string;
  reachable: boolean;
  on?: boolean | null;
  aqi?: number | null;
  mode?: string | null;
  battery_level?: number | null;
  status?: string | null;
  cleaning?: boolean | null;
  charging?: boolean | null;
  filter_life_remaining?: number | null;
  error?: string | null;
  source?: "device" | "homekit";
};

function iconFor(kind: string): LucideIcon {
  switch (kind) {
    case "air_purifier":
    case "airpurifier":
      return Wind;
    case "vacuum":
      return Disc3;
    case "light":
    case "switch":
      return Lightbulb;
    case "lock":
      return Lock;
    case "thermostat":
    case "temperature":
      return Thermometer;
    case "fan":
      return Fan;
    default:
      return Power;
  }
}

function statusLine(d: DeviceSnap): string {
  if (!d.reachable) return d.error ? "Error" : "Offline";
  if (d.kind === "vacuum" || d.kind.includes("vacuum")) {
    if (d.cleaning) return "Cleaning";
    if (d.charging) return "Docked";
    return d.status || "Idle";
  }
  if (d.kind.includes("purifier") || d.kind === "air_purifier") {
    if (d.on) return d.aqi != null ? `AQI ${d.aqi}` : "On";
    return "Off";
  }
  if (d.on === true) return "On";
  if (d.on === false) return "Off";
  if (d.status) return d.status;
  return "Ready";
}

function isActive(d: DeviceSnap): boolean {
  if (!d.reachable) return false;
  if (d.cleaning) return true;
  return d.on === true;
}

export async function sendDeviceCommand(
  id: string,
  action: string,
  args: Record<string, unknown> = {}
): Promise<{ ok: boolean; error?: string }> {
  try {
    const r = await fetch(`/api/devices/devices/${encodeURIComponent(id)}/command`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action, args }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j?.ok === false) {
      return { ok: false, error: j?.error || `${r.status}` };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export function DeviceTile({
  d,
  onAction,
  busy,
}: {
  d: DeviceSnap;
  onAction?: (d: DeviceSnap, action: string) => void;
  busy?: boolean;
}) {
  const Icon = iconFor(d.kind);
  const active = isActive(d);
  const offline = !d.reachable;

  const primaryAction = (): string | null => {
    if (d.source === "homekit") return null; // read-only until HK control API
    const kind = (d.kind || "").toLowerCase();
    if (kind.includes("purifier")) {
      // drivers accept on/off (and turn_on/turn_off aliases)
      return d.on ? "off" : "on";
    }
    if (kind.includes("vacuum")) {
      return d.cleaning ? "stop" : "start";
    }
    if (d.on != null) return d.on ? "off" : "on";
    return null;
  };

  const action = primaryAction();

  return (
    <button
      type="button"
      disabled={busy || offline || !action}
      onClick={() => action && onAction?.(d, action)}
      className={clsx(
        "group relative flex min-h-[132px] flex-col items-start rounded-tile border p-4 text-left transition",
        "disabled:cursor-not-allowed",
        offline
          ? "border-white/[0.05] bg-white/[0.02] opacity-60"
          : active
            ? "border-accent/40 bg-accent/[0.12] shadow-glow"
            : "border-white/[0.08] bg-white/[0.03] hover:bg-white/[0.055]"
      )}
    >
      <div className="flex w-full items-start justify-between gap-2">
        <span
          className={clsx(
            "flex h-9 w-9 items-center justify-center rounded-xl",
            active ? "bg-accent/25 text-accent" : "bg-white/[0.06] text-fg-secondary"
          )}
        >
          <Icon size={18} strokeWidth={2} />
        </span>
        <span
          className={clsx(
            "mt-1 h-2 w-2 rounded-full",
            offline
              ? "bg-danger"
              : d.cleaning
                ? "bg-info animate-pulse"
                : active
                  ? "bg-success"
                  : "bg-fg-faint"
          )}
        />
      </div>

      <div className="mt-auto w-full pt-6">
        <div className="truncate text-[15px] font-medium tracking-tight text-fg">
          {d.name}
        </div>
        <div className="mt-0.5 flex items-center justify-between gap-2 text-[12px] text-fg-muted">
          <span className="truncate">{statusLine(d)}</span>
          {d.battery_level != null && (
            <span className="inline-flex items-center gap-0.5 text-fg-faint">
              <Battery size={12} />
              {d.battery_level}%
            </span>
          )}
        </div>
        {d.room && d.room !== "Default Room" && (
          <div className="mt-1 text-[11px] text-fg-faint">{d.room}</div>
        )}
        {d.filter_life_remaining != null && d.filter_life_remaining < 20 && (
          <div className="mt-1 text-[11px] text-warn">Filter {d.filter_life_remaining}%</div>
        )}
      </div>
    </button>
  );
}

export function SceneChip({
  label,
  hint,
  onClick,
  active,
}: {
  label: string;
  hint?: string;
  onClick?: () => void;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "shrink-0 rounded-chip border px-4 py-2 text-left transition",
        active
          ? "border-accent/50 bg-accent/20 text-fg"
          : "border-white/[0.08] bg-white/[0.03] text-fg-secondary hover:bg-white/[0.06]"
      )}
    >
      <div className="text-[13px] font-medium">{label}</div>
      {hint && <div className="text-[11px] text-fg-faint">{hint}</div>}
    </button>
  );
}

export function StatusStat({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "neutral" | "ok" | "warn" | "bad" | "info";
}) {
  const valueClass =
    tone === "ok"
      ? "text-success"
      : tone === "warn"
        ? "text-warn"
        : tone === "bad"
          ? "text-danger"
          : tone === "info"
            ? "text-info"
            : "text-fg";
  return (
    <div className="min-w-0 flex-1 rounded-tile border border-white/[0.08] bg-white/[0.03] px-3 py-3">
      <div className="text-[11px] font-medium uppercase tracking-wider text-fg-faint">
        {label}
      </div>
      <div className={clsx("mt-1 truncate text-lg font-semibold tracking-tight", valueClass)}>
        {value}
      </div>
    </div>
  );
}
