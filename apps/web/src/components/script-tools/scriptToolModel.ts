export type ScriptToolItem = {
  id: string;
  caseId: string;
  title: string;
  script: string;
  source: "sandbox" | "candidate" | "history";
  createdAt: string;
};

export type ScriptToolMode = "generate" | "polish";

// 人设模式：硬广 / IP 人设。后端口播脚本生成会按人设语气改写。
export type PersonaMode = "hard_ad" | "ip_persona";
// 操作类型：润色 / 全新 / 改写 / 复刻 / 生成 / 语义。
export type ScriptOperation = "polish" | "fresh" | "remix" | "clone" | "generate" | "semantic";

export const PERSONA_MODE_OPTIONS: { value: PersonaMode; label: string }[] = [
  { value: "hard_ad", label: "硬广" },
  { value: "ip_persona", label: "IP 人设" },
];

export const SCRIPT_OPERATION_OPTIONS: { value: ScriptOperation; label: string }[] = [
  { value: "polish", label: "润色" },
  { value: "fresh", label: "全新" },
  { value: "remix", label: "改写" },
  { value: "clone", label: "复刻" },
  { value: "generate", label: "生成" },
  { value: "semantic", label: "语义" },
];

export const DEFAULT_PERSONA_MODE: PersonaMode = "hard_ad";
export const DEFAULT_SCRIPT_OPERATION: ScriptOperation = "generate";

const PERSONA_MODE_LABELS = Object.fromEntries(PERSONA_MODE_OPTIONS.map((item) => [item.value, item.label]));
const SCRIPT_OPERATION_LABELS = Object.fromEntries(SCRIPT_OPERATION_OPTIONS.map((item) => [item.value, item.label]));

export function newScriptToolId(prefix: string) {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return `${prefix}_${crypto.randomUUID()}`;
  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

export function trimScriptToolList(items: ScriptToolItem[], limit = 30) {
  return [...items]
    .sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt))
    .slice(0, limit);
}

export function buildGenerationBrief({
  mode,
  personaMode,
  operation,
  goal,
  topic,
  currentScript,
  index,
}: {
  mode: ScriptToolMode;
  personaMode: PersonaMode;
  operation: ScriptOperation;
  goal: string;
  topic: string;
  currentScript: string;
  index: number;
}) {
  const lines = [
    mode === "polish" ? "请润色当前脚本，保留事实与核心卖点。" : "请生成一版新的短视频脚本。",
    // persona_mode/operation 同时作为独立字段发送（见 ScriptGenerateModal），此处保留文本提示便于 sandbox 模型读取。
    `人设模式：${PERSONA_MODE_LABELS[personaMode] ?? personaMode}`,
    `操作：${SCRIPT_OPERATION_LABELS[operation] ?? operation}`,
    goal.trim() ? `目标：${goal.trim()}` : "",
    topic.trim() ? `主题提示：${topic.trim()}` : "",
    currentScript.trim() ? `当前脚本：${currentScript.trim()}` : "",
    `版本序号：${index + 1}`,
  ].filter(Boolean);
  return `${lines.join("\n")}\n\n请输出可直接用于数字人视频的中文口播脚本。`;
}
