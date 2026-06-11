import { Download, Eye, Loader2, Play, RefreshCw, Trash2 } from "lucide-react";
import type { MediaAssetCard } from "../../api/client";
import { shortId } from "../../lib/format";
import { annotationStatusLabels, annotationTone } from "./libraryModel";

type TemplateAssetCardProps = {
  card: MediaAssetCard;
  previewUrl: string | null;
  batchMode: boolean;
  selected: boolean;
  isAnalyzing: boolean;
  onToggleSelected: () => void;
  onPreview: () => void;
  onAnalyze: () => void;
  onOpenAnnotation: () => void;
};

export function TemplateAssetCard({
  card,
  previewUrl,
  batchMode,
  selected,
  isAnalyzing,
  onToggleSelected,
  onPreview,
  onAnalyze,
  onOpenAnnotation,
}: TemplateAssetCardProps) {
  const asset = card.asset;
  return (
    <article
      className={`group rounded-[24px] border bg-white/65 p-3 shadow-glow transition-all hover:-translate-y-0.5 ${
        selected ? "border-accent/40" : "border-border/80 hover:border-accent/25"
      }`}
    >
      <div className="relative overflow-hidden rounded-2xl bg-[#151913]">
        {batchMode ? (
          <label className="absolute left-2 top-2 z-10 flex h-8 w-8 items-center justify-center rounded-xl bg-white/90">
            <input type="checkbox" checked={selected} onChange={onToggleSelected} aria-label="选择素材" />
          </label>
        ) : null}
        {previewUrl ? (
          <video
            src={previewUrl}
            muted
            loop
            playsInline
            preload="metadata"
            className="aspect-video w-full object-cover opacity-90 transition-opacity group-hover:opacity-100"
            onMouseEnter={(event) => void event.currentTarget.play().catch(() => undefined)}
            onMouseLeave={(event) => event.currentTarget.pause()}
          />
        ) : (
          <button type="button" onClick={onPreview} className="flex aspect-video w-full items-center justify-center text-white/75">
            <Play className="h-9 w-9" />
          </button>
        )}
        <span className="absolute bottom-2 right-2 rounded-full bg-black/70 px-2 py-1 text-xs text-white">预览</span>
      </div>
      <div className="mt-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold text-text-primary">{asset.title}</h3>
          <p className="mt-1 font-mono text-xs text-text-tertiary">{shortId(asset.id, 12)}</p>
        </div>
        <span className={`badge ${annotationTone(asset.annotation_status)}`}>
          {annotationStatusLabels[asset.annotation_status]}
        </span>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {(asset.tags ?? []).slice(0, 4).map((tag) => (
          <span key={tag} className="badge bg-surface-hover text-text-secondary">
            {tag}
          </span>
        ))}
      </div>
      <div className="mt-4 grid grid-cols-4 gap-2">
        <button className="icon-button w-full" type="button" onClick={onAnalyze} disabled={isAnalyzing} title="重新分析">
          {isAnalyzing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
        </button>
        <button className="icon-button w-full" type="button" onClick={onOpenAnnotation} title="查看标注">
          <Eye className="h-4 w-4" />
        </button>
        <a className={`icon-button w-full ${previewUrl ? "" : "pointer-events-none opacity-50"}`} href={previewUrl ?? undefined} download title="下载">
          <Download className="h-4 w-4" />
        </a>
        <button className="icon-button w-full" type="button" disabled title="后端暂无素材删除 API">
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
    </article>
  );
}
