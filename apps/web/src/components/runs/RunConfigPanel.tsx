import type { RunConfigSummary } from "../../api/client";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1">
      <p className="text-xs text-text-tertiary">{label}</p>
      <div className="text-sm font-medium text-text-primary">{children}</div>
    </div>
  );
}

function toggleBadge(label: string, enabled: boolean | null | undefined) {
  if (enabled == null) return null;
  return (
    <span key={label} className={`badge ${enabled ? "badge-success" : "bg-black/5 text-text-tertiary"}`}>
      {label}
      {enabled ? " 开" : " 关"}
    </span>
  );
}

/** 生成配置：把发起本次成片的任务输入（任务ID、标题、音色、脚本文案等）原样展示。 */
export function RunConfigPanel({ config, runId }: { config?: RunConfigSummary | null; runId: string }) {
  const fullRunId = config?.run_id || runId;
  const dims =
    config?.width && config?.height ? `${config.width} × ${config.height}${config.fps ? ` · ${config.fps}fps` : ""}` : null;

  return (
    <section className="grid gap-3 rounded-2xl border border-border/70 bg-white/60 p-4">
      <h4 className="text-base font-semibold text-text-primary">生成配置</h4>

      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="任务 ID">
          <span className="font-mono text-xs break-all">{fullRunId}</span>
        </Field>
        {config?.job_id ? (
          <Field label="作业 ID">
            <span className="font-mono text-xs break-all">{config.job_id}</span>
          </Field>
        ) : null}
        {config?.title ? <Field label="标题">{config.title}</Field> : null}
        {config?.voice_id ? (
          <Field label="音色">
            <span className="font-mono text-xs">{config.voice_id}</span>
            {config.voice_provider_profile_id ? (
              <span className="ml-2 text-xs text-text-tertiary">{config.voice_provider_profile_id}</span>
            ) : null}
            {config.voice_speed != null || config.voice_emotion ? (
              <span className="ml-2 text-xs text-text-tertiary">
                {config.voice_speed != null ? `语速 ${config.voice_speed}×` : ""}
                {config.voice_emotion && config.voice_emotion !== "neutral" ? ` · ${config.voice_emotion}` : ""}
              </span>
            ) : null}
          </Field>
        ) : null}
        {dims ? <Field label="分辨率">{dims}</Field> : null}
      </div>

      {config?.subtitle_enabled != null || config?.broll_enabled != null || config?.lipsync_enabled != null ? (
        <div className="flex flex-wrap gap-2">
          {toggleBadge("字幕", config?.subtitle_enabled)}
          {toggleBadge("B-roll", config?.broll_enabled)}
          {toggleBadge("口型同步", config?.lipsync_enabled)}
        </div>
      ) : null}

      {config?.script ? (
        <div className="grid gap-1">
          <p className="text-xs text-text-tertiary">脚本文案</p>
          <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded-xl border border-border/70 bg-surface-hover p-3 text-sm leading-relaxed text-text-primary">
            {config.script}
          </pre>
        </div>
      ) : null}

      {config?.publish_content ? (
        <div className="grid gap-1">
          <p className="text-xs text-text-tertiary">发布文案</p>
          <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-xl border border-border/70 bg-surface-hover p-3 text-sm leading-relaxed text-text-secondary">
            {config.publish_content}
          </pre>
        </div>
      ) : null}
    </section>
  );
}
