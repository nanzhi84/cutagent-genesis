import type { AuthUser, RegistrationCodePreview } from "../../api/client";
import { formatAbsoluteTime } from "../../lib/format";

export const roleOptions: Array<{ value: AuthUser["role"]; label: string }> = [
  { value: "viewer", label: "查看成员" },
  { value: "operator", label: "运营成员" },
  { value: "admin", label: "管理员" },
];

export const userStatusOptions: Array<{ value: AuthUser["status"]; label: string }> = [
  { value: "active", label: "启用" },
  { value: "disabled", label: "停用" },
];

export const codeStatusOptions: Array<{ value: RegistrationCodePreview["status"]; label: string }> = [
  { value: "active", label: "启用" },
  { value: "disabled", label: "停用" },
  { value: "expired", label: "过期" },
];

export function roleLabel(role?: string) {
  return roleOptions.find((item) => item.value === role)?.label ?? "未知角色";
}

export function userStatusLabel(status?: string) {
  return userStatusOptions.find((item) => item.value === status)?.label ?? "未知状态";
}

export function codeStatusLabel(status?: string) {
  return codeStatusOptions.find((item) => item.value === status)?.label ?? "未知状态";
}

export function isAdmin(user?: AuthUser | null) {
  return user?.role === "admin";
}

export function displayTime(value?: string | null) {
  return value ? formatAbsoluteTime(value) : "暂无";
}

export function toDateTimeLocal(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const offsetMs = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

export function fromDateTimeLocal(value: string) {
  return value ? new Date(value).toISOString() : null;
}
