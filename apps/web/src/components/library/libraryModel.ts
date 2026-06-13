import { FileAudio, Library, Mic2, Music4 } from "lucide-react";
import type { MediaAssetCard, MediaAssetRecord, VoiceProfile } from "../../api/client";
import { toDisplayUrl as sanitizeDisplayUrl } from "../../lib/url";

export const VOICE_UPLOAD_ACCEPT = ".mp3,.wav,.m4a,.aac,.ogg,.flac";

export type LibraryTab = "voices" | "templates" | "fonts" | "bgm";
export type VoiceSourceFilter = "all" | VoiceProfile["source"];
export type TemplateKind = "portrait" | "broll";
export type LibraryAssetKind = "font" | "bgm";

export type UploadPlaceholder = {
  id: string;
  name: string;
  kind: TemplateKind;
  status: "uploading" | "failed";
  progress: number;
  error?: string;
};

export const libraryTabs: Array<{ id: LibraryTab; label: string; to: string; icon: typeof Mic2 }> = [
  { id: "voices", label: "音色", to: "/library/voices", icon: Mic2 },
  { id: "templates", label: "视频模板", to: "/library/templates", icon: Library },
  { id: "fonts", label: "字体", to: "/library/fonts", icon: FileAudio },
  { id: "bgm", label: "BGM", to: "/library/bgm", icon: Music4 },
];

export const voiceSourceLabels: Record<VoiceProfile["source"], string> = {
  builtin: "系统音色",
  cloned: "克隆音色",
  designed: "设计音色",
};

export const templateKindLabels: Record<TemplateKind, string> = {
  portrait: "人像模板",
  broll: "B-roll",
};

export const annotationStatusLabels: Record<MediaAssetRecord["annotation_status"], string> = {
  pending: "待标注",
  annotated: "已标注",
  annotation_failed: "标注失败",
};

export const libraryAssetLabels: Record<LibraryAssetKind, string> = {
  font: "字体",
  bgm: "BGM",
};

export function readTab(pathname: string): LibraryTab | null {
  const segment = pathname.split("/").filter(Boolean).at(-1);
  if (segment === "voices" || segment === "templates" || segment === "fonts" || segment === "bgm") return segment;
  return null;
}

export function sourceTone(source: VoiceProfile["source"]) {
  if (source === "builtin") return "badge-info";
  if (source === "cloned") return "badge-success";
  return "badge-warning";
}

export function annotationTone(status: MediaAssetRecord["annotation_status"]) {
  if (status === "annotated") return "badge-success";
  if (status === "annotation_failed") return "badge-error";
  return "badge-warning";
}

export function emptyVoiceDraft() {
  return {
    name: "",
    prompt: "",
    text: "欢迎使用树影素材库，这是音色试听文本。",
    providerProfileId: "",
  };
}

export function collectUsefulTags(items: MediaAssetCard[], excluded: string[]) {
  const excludedSet = new Set(excluded);
  const tags = new Set<string>();
  items.forEach((card) => {
    card.asset.tags?.forEach((tag) => {
      if (!excludedSet.has(tag)) tags.add(tag);
    });
  });
  return Array.from(tags).sort((a, b) => a.localeCompare(b, "zh-Hans-CN"));
}

export function fontFamilyName(assetId: string) {
  return `cutagent-font-${assetId.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
}

export function uploadStageLabel(status: string) {
  if (status === "preparing") return "准备上传";
  if (status === "uploading") return "传输文件";
  if (status === "completing") return "写入素材";
  if (status === "completed") return "已完成";
  if (status === "failed") return "失败";
  return "等待";
}

/** 仅 http(s) 或站内相对路径可直接作为浏览器资源 URL；内部 scheme（local:// 等）回退占位。 */
export function toDisplayUrl(url: string | null | undefined): string | null {
  return sanitizeDisplayUrl(url);
}
