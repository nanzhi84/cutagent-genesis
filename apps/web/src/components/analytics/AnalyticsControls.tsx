import { analyticsTabs, rangeOptions, type AnalyticsTab, type TimeRange } from "./analyticsModel";

export function RangeSegmentedControl({
  value,
  onChange,
}: {
  value: TimeRange;
  onChange: (value: TimeRange) => void;
}) {
  return (
    <div className="flex items-center gap-1 rounded-2xl border border-border bg-white/65 p-1">
      {rangeOptions.map((range) => (
        <button
          className={`min-h-9 rounded-xl px-3 text-sm font-medium transition-colors ${
            value === range.key ? "bg-accent text-white" : "text-text-secondary hover:bg-white hover:text-text-primary"
          }`}
          key={range.key}
          type="button"
          onClick={() => onChange(range.key)}
        >
          {range.label}
        </button>
      ))}
    </div>
  );
}

export function AnalyticsTabs({
  value,
  onChange,
}: {
  value: AnalyticsTab;
  onChange: (value: AnalyticsTab) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2 border-b border-border/60 pb-3" role="tablist" aria-label="数据统计分区">
      {analyticsTabs.map((tab) => (
        <button
          aria-selected={value === tab.key}
          className={`inline-flex min-h-10 items-center rounded-2xl px-4 py-2 text-sm font-medium transition-colors ${
            value === tab.key
              ? "bg-brand-amber text-text-primary shadow-[0_8px_20px_rgba(214,255,72,0.25)]"
              : "border border-border/70 bg-white/55 text-text-secondary hover:bg-white/80 hover:text-text-primary"
          }`}
          key={tab.key}
          role="tab"
          type="button"
          onClick={() => onChange(tab.key)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
