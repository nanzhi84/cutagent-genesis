import type { OpsDashboardVm, RunCard, YieldFunnelEvent } from "../../api/client";

export type OverviewStats = {
  total: number;
  processing: number;
  completed: number;
  failed: number;
};

type RunStatusBucket = "processing" | "completed" | "failed" | "other";

function bucketRunStatus(status: string): RunStatusBucket {
  if (status === "succeeded" || status === "completed") return "completed";
  if (status === "failed" || status === "cancelled") return "failed";
  if (status === "created" || status === "admitted" || status === "running" || status === "cancelling") {
    return "processing";
  }
  return "other";
}

function normalizeWorkflowStatus(eventType: string) {
  return eventType.startsWith("workflow_") ? eventType.slice("workflow_".length) : eventType;
}

function eventIdentity(event: YieldFunnelEvent) {
  return event.run_id || event.job_id || event.dedupe_key || event.id;
}

function statsFromYieldEvents(events: YieldFunnelEvent[]): OverviewStats | null {
  if (events.length === 0) return null;
  const latestByRun = new Map<string, YieldFunnelEvent>();
  events.forEach((event) => {
    const key = eventIdentity(event);
    const current = latestByRun.get(key);
    if (!current || Date.parse(event.event_time) >= Date.parse(current.event_time)) {
      latestByRun.set(key, event);
    }
  });

  const stats: OverviewStats = { total: 0, processing: 0, completed: 0, failed: 0 };
  latestByRun.forEach((event) => {
    const bucket = bucketRunStatus(normalizeWorkflowStatus(event.event_type));
    if (bucket === "other") return;
    stats.total += 1;
    stats[bucket] += 1;
  });
  return stats.total > 0 ? stats : null;
}

function statsFromRunCards(runs: RunCard[]): OverviewStats {
  const stats: OverviewStats = { total: runs.length, processing: 0, completed: 0, failed: 0 };
  runs.forEach((run) => {
    const bucket = bucketRunStatus(run.status);
    if (bucket !== "other") stats[bucket] += 1;
  });
  return stats;
}

export function buildOverviewStats(dashboard: OpsDashboardVm | undefined, runs: RunCard[]): OverviewStats {
  return statsFromYieldEvents(dashboard?.yield_funnel.events ?? []) ?? statsFromRunCards(runs);
}

export function sortRecentRuns(runs: RunCard[]) {
  return [...runs].sort((left, right) => {
    const leftTime = Date.parse(left.updatedAt ?? left.startedAt ?? "");
    const rightTime = Date.parse(right.updatedAt ?? right.startedAt ?? "");
    return (Number.isNaN(rightTime) ? 0 : rightTime) - (Number.isNaN(leftTime) ? 0 : leftTime);
  });
}
