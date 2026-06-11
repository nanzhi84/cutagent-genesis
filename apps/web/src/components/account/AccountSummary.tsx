import { Shield } from "lucide-react";
import type { AuthUser } from "../../api/client";
import { displayTime, roleLabel, userStatusLabel } from "./accountModel";

export function AccountSummary({ user }: { user: AuthUser | null }) {
  const items = [
    { label: "邮箱", value: user?.email ?? "-" },
    { label: "显示名称", value: user?.display_name || "-" },
    { label: "角色", value: roleLabel(user?.role) },
    { label: "状态", value: userStatusLabel(user?.status) },
    { label: "创建时间", value: displayTime(user?.created_at) },
  ];

  return (
    <section className="card">
      <div className="inline-flex items-center gap-2 rounded-full border border-accent/20 bg-accent/10 px-3 py-1 text-xs font-medium text-accent">
        <Shield className="h-4 w-4" />
        账户中心
      </div>
      <h1 className="mt-4 font-display text-3xl text-text-primary">注册、登录和账户管理</h1>
      <p className="mt-3 max-w-3xl text-sm leading-6 text-text-secondary">
        维护个人资料和密码。管理员可以继续管理成员账户与注册码。
      </p>
      <div className="mt-8 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        {items.map((item) => (
          <div className="rounded-2xl border border-border bg-background-secondary p-4" key={item.label}>
            <div className="text-xs text-text-tertiary">{item.label}</div>
            <div className="mt-3 truncate text-sm font-medium text-text-primary" title={item.value}>
              {item.value}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
