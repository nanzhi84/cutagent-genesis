import { CheckCircle2, Edit3, Loader2, Plus, RefreshCw, Scissors, Trash2 } from "lucide-react";
import { useEffect, useState, type Dispatch, type SetStateAction } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, isApiError, type AnnotationEditorVm } from "../../api/client";
import { formatDuration, shortId } from "../../lib/format";
import { Modal } from "../ui/Modal";
import { useToast } from "../ui/Toast";

type InvalidSegment = {
  start_sec: number;
  end_sec: number;
  reason: string;
};

type AnnotationForm = {
  qualityStatus: string;
  usable: boolean;
  invalidSegments: InvalidSegment[];
  segmentsJson: string;
};

type AnnotationEditorModalProps = {
  assetId: string | null;
  caseId: string | null;
  onClose: () => void;
};

export function AnnotationEditorModal({ assetId, caseId, onClose }: AnnotationEditorModalProps) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [rerunPreview, setRerunPreview] = useState(false);
  const [form, setForm] = useState<AnnotationForm>({
    qualityStatus: "usable",
    usable: true,
    invalidSegments: [],
    segmentsJson: "[]",
  });

  const editorQuery = useQuery({
    queryKey: ["library", "annotation", assetId],
    queryFn: () => api.annotations.get(assetId!),
    enabled: Boolean(assetId),
  });

  const editor = editorQuery.data ?? null;

  useEffect(() => {
    if (!editor) return;
    const projection = editor.projection;
    const canonical = editor.canonical;
    const segments = readJsonArray(projection, "segments");
    const fallbackSegments = segments.length > 0 ? segments : readJsonArray(canonical, "segments");
    setForm({
      qualityStatus: readJsonString(projection, "quality_status") || (editor.asset.usable ? "usable" : "review"),
      usable: editor.asset.usable,
      invalidSegments: normalizeInvalidSegments(readJsonArray(projection, "invalid_segments")),
      segmentsJson: JSON.stringify(fallbackSegments, null, 2),
    });
    setEditing(false);
    setRerunPreview(false);
  }, [editor]);

  const patchMutation = useMutation({
    mutationFn: async () => {
      if (!assetId || !editor) throw new Error("标注未加载");
      const parsedSegments = parseSegmentsJson(form.segmentsJson);
      return api.annotations.patch(assetId, {
        etag: editor.etag,
        patch: {
          operations: [
            { op: "replace", path: "/projection/quality_status", value: form.qualityStatus },
            { op: "replace", path: "/projection/usable", value: form.usable },
            { op: "replace", path: "/projection/invalid_segments", value: form.invalidSegments },
            { op: "replace", path: "/projection/segments", value: parsedSegments },
          ],
        },
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["library", "annotation", assetId] });
      await queryClient.invalidateQueries({ queryKey: ["library", "media", caseId] });
      toast.success("标注已保存", "素材标注状态已更新。");
      setEditing(false);
    },
    onError: (error) => {
      if (isApiError(error) && (error.status === 409 || error.code === "artifact.schema_mismatch")) {
        toast.error("标注版本冲突", "服务器标注已更新，请刷新后重新编辑。");
        return;
      }
      toast.error("标注保存失败", error);
    },
  });

  const rerunMutation = useMutation({
    mutationFn: () => {
      if (!assetId) throw new Error("标注未加载");
      return api.annotations.rerun(assetId, { force: true });
    },
    onSuccess: async (response) => {
      await queryClient.invalidateQueries({ queryKey: ["library", "annotation", assetId] });
      await queryClient.invalidateQueries({ queryKey: ["library", "media", caseId] });
      toast.success("重新分析已提交", response.run_id ? `运行 ID：${shortId(response.run_id)}` : "沙箱环境已返回完成状态");
      setRerunPreview(false);
    },
    onError: (error) => toast.error("重新分析失败", error),
  });

  const trimMutation = useMutation({
    mutationFn: () => {
      if (!assetId) throw new Error("标注未加载");
      return api.annotations.trim(assetId, {});
    },
    onSuccess: async (response) => {
      await queryClient.invalidateQueries({ queryKey: ["library", "annotation", assetId] });
      await queryClient.invalidateQueries({ queryKey: ["library", "media", caseId] });
      toast.success("裁剪完成", `有效时长 ${formatDuration(response.valid_duration_sec)}`);
    },
    onError: (error) => toast.error("裁剪失败", error),
  });

  const projection = editor?.projection ?? {};
  const canonical = editor?.canonical ?? {};
  const segments = readJsonArray(projection, "segments");
  const qualityEvents = readJsonArray(projection, "quality_events");
  const invalidSegments = normalizeInvalidSegments(readJsonArray(projection, "invalid_segments"));
  const invalidDuration = invalidSegments.reduce((sum, item) => sum + Math.max(0, item.end_sec - item.start_sec), 0);
  const validDuration = readJsonNumber(projection, "valid_duration_sec") ?? readJsonNumber(projection, "usable_duration_sec");
  const totalDuration = readJsonNumber(projection, "duration_sec") ?? (validDuration !== undefined ? validDuration + invalidDuration : undefined);

  return (
    <Modal isOpen={Boolean(assetId)} onClose={onClose} title="标注编辑器" size="2xl">
      {editorQuery.isLoading ? (
        <div className="grid min-h-[360px] place-items-center text-text-secondary">
          <Loader2 className="h-6 w-6 animate-spin" />
        </div>
      ) : null}
      {editorQuery.error ? (
        <div className="rounded-2xl border border-status-error/30 bg-status-error/10 p-4 text-sm text-status-error">
          标注加载失败：{String(editorQuery.error)}
        </div>
      ) : null}
      {editor ? (
        <div className="grid gap-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="text-lg font-semibold text-text-primary">{editor.asset.title}</h3>
              <p className="mt-1 font-mono text-xs text-text-tertiary">
                {shortId(editor.asset.id, 14)} · 版本标识 {shortId(editor.etag, 14)}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button className="btn-secondary" type="button" onClick={() => setRerunPreview(true)} disabled={rerunMutation.isPending}>
                <RefreshCw className="h-4 w-4" />
                <span>重新分析</span>
              </button>
              <button className="btn-secondary" type="button" onClick={() => trimMutation.mutate()} disabled={trimMutation.isPending}>
                {trimMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Scissors className="h-4 w-4" />}
                <span>裁剪无效片段</span>
              </button>
              <button className="btn-primary" type="button" onClick={() => setEditing((value) => !value)}>
                <Edit3 className="h-4 w-4" />
                <span>{editing ? "查看只读" : "手动编辑"}</span>
              </button>
            </div>
          </div>

          {rerunPreview ? (
            <div className="rounded-2xl border border-status-warning/25 bg-status-warning/10 p-4">
              <h4 className="text-sm font-semibold text-status-warning">重新分析预览</h4>
              <p className="mt-2 text-sm text-status-warning">
                将基于当前素材重新生成标注结果。确认覆盖后，现有人工编辑可能被新结果替换；放弃会保留当前版本标识与编辑内容。
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button className="btn-primary min-h-9 px-3" type="button" onClick={() => rerunMutation.mutate()} disabled={rerunMutation.isPending}>
                  {rerunMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                  <span>确认覆盖</span>
                </button>
                <button className="btn-secondary min-h-9 px-3" type="button" onClick={() => setRerunPreview(false)} disabled={rerunMutation.isPending}>
                  放弃
                </button>
              </div>
            </div>
          ) : null}

          {!editing ? (
            <div className="grid gap-4">
              <div className="grid gap-3 md:grid-cols-3">
                <AnnotationMetric label="有效时长" value={formatDuration(validDuration)} />
                <AnnotationMetric label="无效时长" value={formatDuration(invalidDuration)} />
                <AnnotationMetric label="总时长" value={formatDuration(totalDuration)} />
              </div>
              <div className="grid gap-4 lg:grid-cols-2">
                <AnnotationJsonPanel title="结构化片段" value={segments.length > 0 ? segments : canonical} emptyText="暂无结构化片段" />
                <AnnotationJsonPanel title="质量事件" value={qualityEvents} emptyText="暂无质量事件" />
              </div>
              <AnnotationJsonPanel title="原始标注投影" value={projection} emptyText="暂无投影数据" />
            </div>
          ) : (
            <form
              className="grid gap-4"
              onSubmit={(event) => {
                event.preventDefault();
                patchMutation.mutate();
              }}
            >
              <div className="grid gap-3 md:grid-cols-2">
                <label>
                  <span>质量状态</span>
                  <select value={form.qualityStatus} onChange={(event) => setForm((current) => ({ ...current, qualityStatus: event.target.value }))}>
                    <option value="usable">可用</option>
                    <option value="review">需复核</option>
                    <option value="invalid">不可用</option>
                  </select>
                </label>
                <label className="flex cursor-pointer grid-cols-[auto_minmax(0,1fr)] items-center gap-3 rounded-2xl border border-border/80 bg-white/65 p-3">
                  <input type="checkbox" checked={form.usable} onChange={(event) => setForm((current) => ({ ...current, usable: event.target.checked }))} />
                  <span>
                    <span className="block text-sm font-semibold text-text-primary">允许生产链路复用</span>
                    <span className="mt-1 block text-xs font-normal text-text-secondary">关闭后素材会被标记为不可用。</span>
                  </span>
                </label>
              </div>

              <div className="grid gap-3">
                <div className="flex items-center justify-between gap-3">
                  <h4 className="text-sm font-semibold text-text-primary">无效片段</h4>
                  <button
                    className="btn-secondary min-h-9 px-3"
                    type="button"
                    onClick={() =>
                      setForm((current) => ({
                        ...current,
                        invalidSegments: [...current.invalidSegments, { start_sec: 0, end_sec: 1, reason: "手动标记" }],
                      }))
                    }
                  >
                    <Plus className="h-4 w-4" />
                    <span>新增片段</span>
                  </button>
                </div>
                <div className="grid gap-2">
                  {form.invalidSegments.map((segment, index) => (
                    <div className="grid gap-2 rounded-2xl border border-border/80 bg-white/65 p-3 md:grid-cols-[110px_110px_minmax(0,1fr)_40px]" key={`${segment.start_sec}-${index}`}>
                      <input
                        type="number"
                        min={0}
                        step={0.1}
                        value={segment.start_sec}
                        onChange={(event) => updateInvalidSegment(setForm, index, { start_sec: Number(event.target.value) })}
                        aria-label="开始秒"
                      />
                      <input
                        type="number"
                        min={0}
                        step={0.1}
                        value={segment.end_sec}
                        onChange={(event) => updateInvalidSegment(setForm, index, { end_sec: Number(event.target.value) })}
                        aria-label="结束秒"
                      />
                      <input value={segment.reason} onChange={(event) => updateInvalidSegment(setForm, index, { reason: event.target.value })} aria-label="原因" />
                      <button
                        className="icon-button"
                        type="button"
                        onClick={() => setForm((current) => ({ ...current, invalidSegments: current.invalidSegments.filter((_, itemIndex) => itemIndex !== index) }))}
                        aria-label="删除无效片段"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                  {form.invalidSegments.length === 0 ? <p className="text-sm text-text-secondary">暂无无效片段。</p> : null}
                </div>
              </div>

              <label>
                <span>结构化片段 JSON</span>
                <textarea className="min-h-[220px] font-mono text-xs" value={form.segmentsJson} onChange={(event) => setForm((current) => ({ ...current, segmentsJson: event.target.value }))} />
              </label>

              <div className="rounded-2xl border border-status-warning/20 bg-status-warning/10 p-3 text-xs leading-5 text-status-warning">
                保存会携带当前版本标识；若服务端标注已被更新，将提示版本冲突并要求刷新后重试。
              </div>
              <div className="flex justify-end gap-3 border-t border-border/70 pt-4">
                <button className="btn-secondary" type="button" onClick={() => setEditing(false)} disabled={patchMutation.isPending}>
                  取消编辑
                </button>
                <button className="btn-primary" type="submit" disabled={patchMutation.isPending}>
                  {patchMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                  <span>{patchMutation.isPending ? "保存中" : "保存标注"}</span>
                </button>
              </div>
            </form>
          )}
        </div>
      ) : null}
    </Modal>
  );
}

function AnnotationMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-border/80 bg-white/65 p-4">
      <p className="text-xs text-text-secondary">{label}</p>
      <p className="mt-2 text-lg font-semibold tabular-nums text-text-primary">{value}</p>
    </div>
  );
}

function AnnotationJsonPanel({ title, value, emptyText }: { title: string; value: unknown; emptyText: string }) {
  const isEmpty = Array.isArray(value) ? value.length === 0 : value === null || value === undefined || (typeof value === "object" && Object.keys(value).length === 0);
  return (
    <div className="grid gap-2 rounded-2xl border border-border/80 bg-white/65 p-4">
      <h4 className="text-sm font-semibold text-text-primary">{title}</h4>
      {isEmpty ? <p className="text-sm text-text-secondary">{emptyText}</p> : <pre className="max-h-[320px] text-xs">{JSON.stringify(value, null, 2)}</pre>}
    </div>
  );
}

function readJsonString(source: AnnotationEditorVm["projection"], key: string) {
  const value = source[key];
  return typeof value === "string" ? value : undefined;
}

function readJsonNumber(source: AnnotationEditorVm["projection"], key: string) {
  const value = source[key];
  return typeof value === "number" ? value : undefined;
}

function readJsonArray(source: AnnotationEditorVm["projection"], key: string): unknown[] {
  const value = source[key];
  return Array.isArray(value) ? value : [];
}

function normalizeInvalidSegments(values: unknown[]): InvalidSegment[] {
  return values
    .map((value) => {
      const record = typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
      const start = Number(record.start_sec ?? record.start ?? 0);
      const end = Number(record.end_sec ?? record.end ?? start);
      const reason = typeof record.reason === "string" ? record.reason : "未说明";
      return {
        start_sec: Number.isFinite(start) ? start : 0,
        end_sec: Number.isFinite(end) ? end : 0,
        reason,
      };
    })
    .filter((value) => value.end_sec >= value.start_sec);
}

function parseSegmentsJson(value: string) {
  const parsed = JSON.parse(value || "[]") as unknown;
  if (!Array.isArray(parsed)) throw new Error("结构化片段必须是 JSON 数组");
  return parsed;
}

function updateInvalidSegment(setForm: Dispatch<SetStateAction<AnnotationForm>>, index: number, patch: Partial<InvalidSegment>) {
  setForm((current) => ({
    ...current,
    invalidSegments: current.invalidSegments.map((segment, itemIndex) => (itemIndex === index ? { ...segment, ...patch } : segment)),
  }));
}
