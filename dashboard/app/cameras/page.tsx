"use client";

import useSWR from "swr";
import { Shell, SectionLabel } from "../../components/Shell";

const fetcher = (url: string) =>
  fetch(url).then((r) => {
    if (!r.ok) throw new Error(`${r.status}`);
    return r.json();
  });

interface CameraInfo {
  id: string;
  name: string;
  rtsp_url: string;
  hls_url: string | null;
  online: boolean;
  has_motion: boolean;
}

export default function CamerasPage() {
  const { data, error } = useSWR<{ ok: boolean; data: CameraInfo[] }>(
    "/api/agent/cameras",
    fetcher,
    { refreshInterval: 5000 }
  );
  const cameras = data?.data ?? [];
  const motionFirst = [...cameras].sort(
    (a, b) => Number(b.has_motion) - Number(a.has_motion) || Number(b.online) - Number(a.online)
  );

  return (
    <Shell
      title="Cameras"
      subtitle={
        cameras.length
          ? `${cameras.filter((c) => c.online).length} online · ${cameras.filter((c) => c.has_motion).length} motion`
          : "Local streams"
      }
    >
      {error && (
        <div className="mb-6 rounded-tile border border-warn/30 bg-warn/10 px-4 py-3 text-sm text-fg-secondary">
          Cameras service not reachable. Start the cameras agent and ONVIF-discover first.
        </div>
      )}

      {cameras.length === 0 && !error && (
        <div className="rounded-tile border border-white/[0.08] bg-white/[0.03] p-6">
          <h3 className="font-medium">No cameras yet</h3>
          <p className="mt-2 text-sm text-fg-muted">
            Discover ONVIF / RTSP cameras on the LAN. Motion events surface here with a red badge.
          </p>
        </div>
      )}

      {motionFirst.some((c) => c.has_motion) && (
        <div className="mb-4">
          <SectionLabel>Motion now</SectionLabel>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {motionFirst.map((c) => (
          <div
            key={c.id}
            className="overflow-hidden rounded-tile border border-white/[0.08] bg-white/[0.03]"
          >
            <div className="relative aspect-video bg-black">
              {c.hls_url ? (
                <video
                  src={c.hls_url}
                  controls
                  playsInline
                  className="h-full w-full object-cover"
                />
              ) : (
                <div className="flex h-full flex-col items-center justify-center gap-1 text-xs text-white/50">
                  <span>{c.online ? "Waiting for HLS" : "Offline"}</span>
                </div>
              )}
              {c.has_motion && (
                <span className="absolute left-3 top-3 rounded-full bg-danger px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
                  Motion
                </span>
              )}
              <span
                className={`absolute right-3 top-3 h-2 w-2 rounded-full ${
                  c.online ? "bg-success" : "bg-fg-faint"
                }`}
              />
            </div>
            <div className="p-3">
              <h3 className="font-medium tracking-tight">{c.name}</h3>
              <p className="mt-0.5 truncate font-mono text-[11px] text-fg-faint">
                {c.online ? "Live path ready" : "Unreachable"}
              </p>
            </div>
          </div>
        ))}
      </div>
    </Shell>
  );
}
