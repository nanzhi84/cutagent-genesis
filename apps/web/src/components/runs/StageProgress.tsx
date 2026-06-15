import { AlertCircle, CheckCircle2, Clock, Loader2 } from "lucide-react";
import type { StageView } from "./runModel";

function stageIcon(status: string) {
  if (status === "succeeded") return <CheckCircle2 className="h-5 w-5 text-status-success" />;
  if (status === "running") return <Loader2 className="h-5 w-5 animate-spin text-accent" />;
  if (status === "failed") return <AlertCircle className="h-5 w-5 text-status-error" />;
  if (status === "degraded") return <AlertCircle className="h-5 w-5 text-status-warning" />;
  return <Clock className="h-5 w-5 text-text-tertiary" />;
}

function stageStatusLabel(status: string) {
  if (status === "succeeded") return "已完成";
  if (status === "running") return "进行中";
  if (status === "failed") return "失败";
  if (status === "degraded") return "已降级";
  return "待执行";
}

function badgeClass(status: string) {
  if (status === "succeeded") return "bg-status-success/15 text-status-success";
  if (status === "running") return "bg-accent/15 text-accent";
  if (status === "failed") return "bg-status-error/15 text-status-error";
  if (status === "degraded") return "bg-status-warning/15 text-status-warning";
  return "bg-black/5 text-text-tertiary";
}

/** 用户友好的生产阶段竖向进度（替代页面级原始节点时间线）。 */
export function StageProgress({ stages }: { stages: StageView[] }) {
  return (
    <ol className="grid gap-2">
      {stages.map((stage) => (
        <li
          key={stage.key}
          className={`flex items-center gap-3 rounded-2xl border p-3 ${
            stage.status === "running" ? "border-accent/30 bg-accent/5 ring-1 ring-accent/20" : "border-border/70 bg-white/60"
          }`}
        >
          <span className="shrink-0">{stageIcon(stage.status)}</span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-text-primary">{stage.label}</p>
            <p className="truncate text-xs text-text-tertiary">{stage.detail}</p>
          </div>
          <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${badgeClass(stage.status)}`}>
            {stageStatusLabel(stage.status)}
          </span>
        </li>
      ))}
    </ol>
  );
}
