/** 仅 http(s) 或站内相对路径可直接作为浏览器资源 URL；内部 scheme（local:// 等）回退占位。 */
export function toDisplayUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  if (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("/")) return url;
  return null;
}
