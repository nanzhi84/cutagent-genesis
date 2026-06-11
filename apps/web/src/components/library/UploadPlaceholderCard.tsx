import { Loader2, PauseCircle } from "lucide-react";
import type { UploadPlaceholder } from "./libraryModel";

export function UploadPlaceholderCard({ item }: { item: UploadPlaceholder }) {
  return (
    <article
      className={`rounded-[24px] border p-4 ${
        item.status === "failed" ? "border-status-error/30 bg-status-error/10" : "border-accent/25 bg-accent/10"
      }`}
    >
      <div className="flex aspect-video items-center justify-center rounded-2xl bg-white/65">
        {item.status === "failed" ? (
          <PauseCircle className="h-8 w-8 text-status-error" />
        ) : (
          <Loader2 className="h-8 w-8 animate-spin text-accent" />
        )}
      </div>
      <h3 className="mt-3 truncate text-sm font-semibold text-text-primary">{item.name}</h3>
      <p className="mt-1 text-xs text-text-secondary">
        {item.status === "failed" ? item.error ?? "上传失败" : "上传中，完成后进入素材网格"}
      </p>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/70">
        <div
          className={`h-full rounded-full ${item.status === "failed" ? "bg-status-error" : "bg-accent"}`}
          style={{ width: `${item.progress}%` }}
        />
      </div>
    </article>
  );
}
