import { KeyRound, ShieldAlert, Ticket, UserCog } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AccountSummary } from "../components/account/AccountSummary";
import { AdminMembersPanel } from "../components/account/AdminMembersPanel";
import { ProfileSecurityPanel } from "../components/account/ProfileSecurityPanel";
import { RegistrationCodesPanel } from "../components/account/RegistrationCodesPanel";
import { isAdmin } from "../components/account/accountModel";
import { useAuth } from "./auth/AuthContext";

type AccountTab = "profile" | "codes" | "members";

export default function AccountPage() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<AccountTab>("profile");
  const admin = isAdmin(user);
  const tabs = useMemo(() => {
    const values: Array<{ key: AccountTab; label: string; icon: typeof KeyRound }> = [
      { key: "profile", label: "个人设置", icon: KeyRound },
    ];
    if (admin) {
      values.push(
        { key: "codes", label: "注册码", icon: Ticket },
        { key: "members", label: "成员管理", icon: UserCog },
      );
    }
    return values;
  }, [admin]);

  useEffect(() => {
    if (!admin && activeTab !== "profile") setActiveTab("profile");
  }, [activeTab, admin]);

  return (
    <div className="space-y-6">
      <AccountSummary user={user} />

      <nav className="flex flex-wrap gap-2 border-b border-border/60 pb-3" role="tablist" aria-label="账户分区">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              aria-selected={activeTab === tab.key}
              className={`inline-flex min-h-10 items-center gap-2 rounded-2xl px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === tab.key
                  ? "bg-brand-amber text-text-primary shadow-[0_8px_20px_rgba(214,255,72,0.25)]"
                  : "border border-border/70 bg-white/55 text-text-secondary hover:bg-white/80 hover:text-text-primary"
              }`}
              key={tab.key}
              role="tab"
              type="button"
              onClick={() => setActiveTab(tab.key)}
            >
              <Icon className="h-4 w-4" />
              {tab.label}
            </button>
          );
        })}
      </nav>

      {activeTab === "profile" ? (
        <>
          <ProfileSecurityPanel user={user} />
          {!admin ? (
            <section className="rounded-[24px] border border-dashed border-border bg-white/45 px-5 py-4">
              <div className="flex items-start gap-3">
                <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-text-tertiary" />
                <div>
                  <h2 className="font-semibold text-text-primary">管理员区已隐藏</h2>
                  <p className="mt-1 text-sm text-text-secondary">当前角色不能管理成员或注册码。</p>
                </div>
              </div>
            </section>
          ) : null}
        </>
      ) : null}
      {admin && activeTab === "codes" ? <RegistrationCodesPanel /> : null}
      {admin && activeTab === "members" ? <AdminMembersPanel currentUser={user} /> : null}
    </div>
  );
}
