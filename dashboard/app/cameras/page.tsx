"use client";

import useSWR from "swr";

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

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <h1 className="mb-6 text-3xl font-semibold">Cameras</h1>
      {error && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-amber-800">
          Cameras service not reachable. Start the cameras agent and ONVIF-discover first.
        </div>
      )}
      {cameras.length === 0 && !error && (
        <p className="text-muted-foreground">No cameras discovered yet.</p>
      )}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {cameras.map((c) => (
          <div key={c.id} className="overflow-hidden rounded-lg border border-border bg-card">
            <div className="aspect-video bg-black/90">
              {c.hls_url ? (
                <video
                  src={c.hls_url}
                  controls
                  className="h-full w-full object-cover"
                />
              ) : (
                <div className="flex h-full items-center justify-center text-xs text-white/60">
                  {c.online ? "HLS not yet configured" : "Offline"}
                </div>
              )}
            </div>
            <div className="p-3">
              <div className="flex items-center justify-between">
                <h3 className="font-medium">{c.name}</h3>
                {c.has_motion && (
                  <span className="rounded-full bg-red-500 px-2 py-0.5 text-[10px] text-white">
                    MOTION
                  </span>
                )}
              </div>
              <p className="text-xs text-muted-foreground">{c.rtsp_url}</p>
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}