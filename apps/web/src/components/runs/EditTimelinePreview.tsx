import { Film, User } from "lucide-react";
import type { RunDetailResponse } from "../../api/client";
import { shortId } from "../../lib/format";

export type EditClip = {
  id: string;
  kind: "portrait" | "broll";
  /** VideoPlayer segment color role: portrait -> main (绿), broll -> cover (青). */
  playerRole: "main" | "cover";
  start: number;
  end: number;
  assetId: string;
  label: string;
  confidence?: number;
  keywords: string[];
};

function formatClock(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  return `${Math.floor(total / 60)}:${(total % 60).toString().padStart(2, "0")}`;
}

/** 合并 plan.portrait（数字人镜头）+ plan.broll（B-roll 插入）为一条带时间戳的剪辑时间线。 */
export function buildEditClips(detail?: RunDetailResponse): EditClip[] {
  const payloads = (detail as (RunDetailResponse & { artifact_payloads?: Record<string, unknown> }) | undefined)?.artifact_payloads;
  const payloadFor = (kind: string) => {
    const artifact = detail?.artifacts.find((item) => item.kind === kind);
    return asRecord(artifact ? payloads?.[artifact.artifact_id] : undefined);
  };
  const clips: EditClip[] = [];

  const portrait = payloadFor("plan.portrait");
  for (const [index, value] of (Array.isArray(portrait?.segments) ? portrait.segments : []).entries()) {
    const row = asRecord(value);
    const assetId = readString(row?.asset_id);
    const start = readNumber(row?.start_sec);
    const end = readNumber(row?.end_sec);
    if (!assetId || start === null || end === null || end <= start) continue;
    clips.push({
      id: readString(row?.segment_id) ?? `portrait-${assetId}-${index}`,
      kind: "portrait",
      playerRole: "main",
      start,
      end,
      assetId,
      label: readString(row?.role) ?? "数字人镜头",
      keywords: [],
    });
  }

  const broll = payloadFor("plan.broll");
  for (const [index, value] of (Array.isArray(broll?.overlays) ? broll.overlays : []).entries()) {
    const row = asRecord(value);
    const assetId = readString(row?.asset_id);
    const start = readNumber(row?.timeline_start);
    const end = readNumber(row?.timeline_end);
    if (!assetId || start === null || end === null || end <= start) continue;
    clips.push({
      id: readString(row?.overlay_id) ?? `broll-${assetId}-${index}`,
      kind: "broll",
      playerRole: "cover",
      start,
      end,
      assetId,
      label: readString(row?.scene_name) ?? readString(row?.reason) ?? "B-roll 片段",
      confidence: readNumber(row?.confidence) ?? undefined,
      keywords: readStringList(row?.matched_keywords),
    });
  }

  return clips.sort((a, b) => a.start - b.start || a.end - b.end);
}

/** 剪辑时间线 / 分镜时间戳：数字人镜头 + B-roll 合并列表，点选与播放器轨道联动。 */
export function EditTimelinePreview({
  clips,
  activeClipId,
  onSelect,
}: {
  clips: EditClip[];
  activeClipId?: string | null;
  onSelect?: (id: string) => void;
}) {
  const brollCount = clips.filter((clip) => clip.kind === "broll").length;
  return (
    <section className="grid gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-base font-semibold text-text-primary">剪辑时间线 · 分镜时间戳</h4>
        <span className="badge bg-white/70 text-text-secondary">
          {clips.length} 个片段 · B-roll {brollCount} 命中
        </span>
      </div>
      {clips.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border bg-white/55 p-5 text-sm font-medium text-text-secondary">
          暂无剪辑片段（成片完成后展示）
        </div>
      ) : (
        <ol className="grid gap-2">
          {clips.map((clip, index) => {
            const active = clip.id === activeClipId;
            return (
              <li key={clip.id}>
                <button
                  type="button"
                  onClick={() => onSelect?.(clip.id)}
                  className={`grid w-full grid-cols-[40px_minmax(0,1fr)_auto] items-center gap-3 rounded-2xl border p-3 text-left transition-colors ${
                    active ? "border-accent/30 bg-accent/5 ring-1 ring-accent/20" : "border-border/70 bg-white/60 hover:bg-white/80"
                  }`}
                >
                  <span
                    className={`flex h-10 w-10 items-center justify-center rounded-xl ${
                      clip.kind === "broll" ? "bg-brand-cyan/20 text-text-secondary" : "bg-accent/15 text-accent"
                    }`}
                  >
                    {clip.kind === "broll" ? <Film className="h-5 w-5" /> : <User className="h-5 w-5" />}
                  </span>
                  <div className="min-w-0">
                    <p className="flex items-center gap-2 text-sm font-semibold text-text-primary">
                      <span className="text-text-tertiary">#{index + 1}</span>
                      <span className="shrink-0 rounded-full bg-surface-hover px-2 py-0.5 text-[11px] font-medium text-text-secondary">
                        {clip.kind === "broll" ? "B-roll" : "数字人"}
                      </span>
                      <span className="font-mono text-xs text-text-tertiary">
                        {formatClock(clip.start)} – {formatClock(clip.end)}
                      </span>
                    </p>
                    <p className="mt-0.5 truncate text-xs text-text-secondary">
                      {clip.label} · <span className="font-mono">{shortId(clip.assetId, 12)}</span>
                    </p>
                    {clip.keywords.length > 0 ? (
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        {clip.keywords.map((keyword) => (
                          <span key={keyword} className="badge bg-surface-hover text-text-secondary">
                            {keyword}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  {clip.confidence != null ? (
                    <span className={`badge ${clip.confidence > 0.7 ? "badge-success" : clip.confidence >= 0.4 ? "badge-warning" : "bg-orange-100 text-orange-700"}`}>
                      {Math.round(clip.confidence * 100)}%
                    </span>
                  ) : (
                    <span className="text-xs text-text-tertiary">主轨</span>
                  )}
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function readNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function readString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function readStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0) : [];
}
