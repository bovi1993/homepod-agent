"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import useSWR from "swr";
import { Activity, Camera, Home as HomeIcon, MessageCircle, Settings, Wind } from "lucide-react";

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

interface DeviceSnap {
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
}

interface Snapshot {
  home_id: string;
  name: string;
  accessories: Accessory[];
  captured_at: number;
}

export default function Page() {
  const { data, error, isLoading } = useSWR<{ ok: boolean; data: Snapshot }>(
    "/api/homekit/state",
    fetcher,
    { refreshInterval: 5000 }
  );
  const { data: devData } = useSWR<{ ok: boolean; data: DeviceSnap[] }>(
    "/api/devices/devices",
    fetcher,
    { refreshInterval: 10000 }
  );
  const [ws, setWs] = useState<WebSocket | null>(null);

  useEffect(() => {
    const url = (process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:51827/ws/state") + "/ws/state";
    const sock = new WebSocket(url);
    sock.onopen = () => setWs(sock);
    sock.onclose = () => setWs(null);
    return () => sock.close();
  }, []);

  const snap = data?.data;
  const accessories = snap?.accessories ?? [];
  const devices = devData?.data ?? [];
  const rooms = Array.from(new Set(accessories.map((a) => a.room)));

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <header className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-semibold">homepod-agent</h1>
          <p className="text-sm text-muted-foreground">
            {snap?.name ?? "Loading…"} · {ws ? "live" : "polling"}
          </p>
        </div>
        <nav className="flex gap-2">
          <NavLink href="/" icon={<HomeIcon size={16} />} label="Home" />
          <NavLink href="/chat" icon={<MessageCircle size={16} />} label="Chat" />
          <NavLink href="/cameras" icon={<Camera size={16} />} label="Cameras" />
          <NavLink href="/settings" icon={<Settings size={16} />} label="Settings" />
        </nav>
      </header>

      {error && (
        <div className="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-red-800">
          Could not reach agent: {String(error.message)}
        </div>
      )}

      {isLoading && <p className="text-muted-foreground">Loading home…</p>}

      {devices.length > 0 && (
        <section className="mb-8">
          <h2 className="mb-4 flex items-center gap-2 text-lg font-medium">
            <Wind size={18} />
            Xiaomi / Dreame · {devices.length}
          </h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {devices.map((d) => (
              <DeviceTile key={d.id} d={d} />
            ))}
          </div>
        </section>
      )}

      {snap && (
        <div className="space-y-8">
          <section>
            <h2 className="mb-4 flex items-center gap-2 text-lg font-medium">
              <Activity size={18} />
              {accessories.length} accessories
            </h2>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {accessories.map((a) => (
                <AccessoryTile key={a.id} a={a} />
              ))}
            </div>
          </section>

          {rooms.length > 0 && (
            <section>
              <h2 className="mb-4 text-lg font-medium">By room</h2>
              <div className="space-y-6">
                {rooms.map((room) => (
                  <div key={room}>
                    <h3 className="mb-2 text-sm font-medium text-muted-foreground">
                      {room}
                    </h3>
                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                      {accessories
                        .filter((a) => a.room === room)
                        .map((a) => (
                          <AccessoryTile key={a.id} a={a} />
                        ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </main>
  );
}

function NavLink({
  href,
  icon,
  label,
}: {
  href: string;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <Link
      href={href}
      className="flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-sm hover:bg-accent/10"
    >
      {icon}
      {label}
    </Link>
  );
}

function AccessoryTile({ a }: { a: Accessory }) {
  const status = a.on === true ? "On" : a.on === false ? "Off" : a.locked ? "Locked" : a.locked === false ? "Unlocked" : "—";
  const dot =
    a.on === true ? "bg-green-500" : a.on === false ? "bg-gray-400" : a.locked === true ? "bg-green-500" : a.locked === false ? "bg-amber-500" : "bg-gray-300";
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-center gap-2">
        <span className={`inline-block h-2.5 w-2.5 rounded-full ${dot}`} />
        <span className="text-sm font-medium">{a.name}</span>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        {a.kind} · {a.room}
      </p>
      <div className="mt-3 flex items-center justify-between text-sm">
        <span className="text-muted-foreground">Status</span>
        <span>{status}</span>
      </div>
      {a.brightness != null && (
        <div className="mt-2 h-1.5 rounded-full bg-border">
          <div
            className="h-full rounded-full bg-accent"
            style={{ width: `${a.brightness}%` }}
          />
        </div>
      )}
      {a.temperature != null && (
        <div className="mt-3 flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Temp</span>
          <span>{a.temperature.toFixed(1)}°C</span>
        </div>
      )}
    </div>
  );
}

function DeviceTile({ d }: { d: DeviceSnap }) {
  const dot = !d.reachable
    ? "bg-red-400"
    : d.cleaning
      ? "bg-blue-500"
      : d.on
        ? "bg-green-500"
        : "bg-gray-400";
  let status = "—";
  if (!d.reachable) status = d.error ? "Down" : "Offline";
  else if (d.kind === "vacuum") {
    status = d.cleaning ? "Cleaning" : d.charging ? "Docked" : d.status || "Idle";
  } else if (d.kind === "air_purifier") {
    status = d.on ? `On · AQI ${d.aqi ?? "—"}` : "Off";
  }
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-center gap-2">
        <span className={`inline-block h-2.5 w-2.5 rounded-full ${dot}`} />
        <span className="text-sm font-medium">{d.name}</span>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        {d.kind} · {d.room}
      </p>
      <div className="mt-3 flex items-center justify-between text-sm">
        <span className="text-muted-foreground">Status</span>
        <span className="text-right">{status}</span>
      </div>
      {d.battery_level != null && (
        <div className="mt-2 flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Battery</span>
          <span>{d.battery_level}%</span>
        </div>
      )}
      {d.filter_life_remaining != null && (
        <div className="mt-2 flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Filter</span>
          <span>{d.filter_life_remaining}%</span>
        </div>
      )}
      {d.mode && (
        <div className="mt-2 flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Mode</span>
          <span>{d.mode}</span>
        </div>
      )}
    </div>
  );
}