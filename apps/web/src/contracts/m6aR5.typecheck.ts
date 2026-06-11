import { api, type AuthUser, type RegistrationCodePreview } from "../api/client";

async function assertR5ApiSurface() {
  const dashboard = await api.ops.dashboard({
    window_start: "2026-06-01T00:00:00Z",
    window_end: "2026-06-12T00:00:00Z",
  });
  const costRollups = await api.ops.costRollups({ group_by: "provider", limit: 20 });
  const funnel = await api.ops.yieldFunnel({});
  const usage = await api.providers.usage({});

  dashboard.usage.invocations satisfies number;
  dashboard.yield_funnel.events[0]?.event_type satisfies string | undefined;
  costRollups.items[0]?.group_key satisfies string | undefined;
  funnel.true_yield_rate satisfies number | null | undefined;
  usage.unpriced_invocation_count satisfies number;

  const registered = await api.auth.register({
    email: "r5@example.test",
    password: "correct horse battery staple",
    display_name: "R5 用户",
    registration_code: "reg_example",
  });
  const me = await api.auth.me();
  const updated = await api.auth.updateMe({ display_name: "R5 用户" });
  const changed = await api.auth.changePassword({
    old_password: "correct horse battery staple",
    new_password: "another correct horse battery staple",
  });
  const users = await api.auth.users({ limit: 20 });
  const createdUser = await api.auth.createUser({
    email: "created-r5@example.test",
    display_name: "新成员",
    role: "viewer",
    password: "correct horse battery staple",
  });
  const patchedUser = await api.auth.patchUser(createdUser.id, { role: "operator", status: "active" });
  const codes = await api.auth.registrationCodes({ limit: 20 });
  const createdCode = await api.auth.createRegistrationCode({ role: "viewer", max_uses: 1 });
  const patchedCode = await api.auth.patchRegistrationCode(createdCode.id, { status: "disabled" });

  registered.user satisfies AuthUser;
  me.email satisfies string;
  updated.display_name satisfies string;
  changed.ok satisfies boolean;
  users.items[0] satisfies AuthUser | undefined;
  patchedUser.role satisfies "admin" | "operator" | "viewer";
  codes.items[0] satisfies RegistrationCodePreview | undefined;
  createdCode.plaintext_code satisfies string;
  patchedCode.status satisfies "active" | "disabled" | "expired";
}

void assertR5ApiSurface;
