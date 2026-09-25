import clsx from "clsx";
import { Chip } from "./ui";

export interface Factor { key: string; label: string; days: number; level: "HIGH" | "MEDIUM" | "LOW"; share_pct: number; evidence: string }

/** Declared shelf life split into: elapsed | lost to conditions | estimated usable. The legal expiry is unchanged. */
export function ShelfLifeTimeline({ declared, elapsed, lost, usable, range }: {
  declared: number; elapsed: number; lost: number; usable: number; range: [number, number];
}) {
  const pct = (v: number) => `${Math.max(0, (100 * v) / declared)}%`;
  const notUsable = declared - usable;
  return (
    <div>
      <div className="grid grid-cols-3 gap-3 mb-4">
        <Stat label="Declared shelf life" value={declared} sub="manufacturer, unchanged" />
        <Stat label="Estimated usable" value={usable} sub={`range ${range[0].toFixed(1)}–${range[1].toFixed(1)} d`} tone="good" />
        <Stat label="Not usable" value={notUsable} sub={`${elapsed.toFixed(1)} elapsed + ${lost.toFixed(1)} lost`} tone="critical" />
      </div>
      <div className="relative">
        <div className="flex h-8 w-full overflow-hidden rounded-md gap-[2px] text-[11px] font-semibold">
          <div className="flex items-center justify-center bg-ink2/15 text-ink2" style={{ width: pct(elapsed) }} title="Elapsed since production">
            {elapsed / declared > 0.12 && `${elapsed.toFixed(1)} d elapsed`}
          </div>
          <div className="flex items-center justify-center text-critical"
            style={{ width: pct(lost), background: "repeating-linear-gradient(45deg, rgb(var(--critical) / .22) 0 6px, rgb(var(--critical) / .10) 6px 12px)" }}
            title="Quality life lost to journey conditions">
            {lost / declared > 0.12 && `${lost.toFixed(1)} d lost`}
          </div>
          <div className="flex items-center justify-center bg-good/25 text-good" style={{ width: pct(usable) }} title="Estimated remaining usable quality window">
            {usable / declared > 0.1 && `${usable.toFixed(1)} d usable`}
          </div>
        </div>
        {/* uncertainty whisker on the lost/usable boundary (the usable window is measured back from the declared expiry) */}
        <div className="relative h-4" title={`Usable-window range ${range[0].toFixed(1)}–${range[1].toFixed(1)} d`}>
          <div className="absolute top-1.5 h-[2px] bg-ink2/60"
            style={{ left: pct(declared - range[1]), width: pct(range[1] - range[0]) }} />
          <div className="absolute top-0.5 h-2.5 w-[2px] bg-ink2/60" style={{ left: pct(declared - range[1]) }} />
          <div className="absolute top-0.5 h-2.5 w-[2px] bg-ink2/60" style={{ left: pct(declared - range[0]) }} />
        </div>
        <div className="flex justify-between text-[11px] text-muted -mt-1">
          <span>Production</span><span>Now</span><span>Declared expiry</span>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, sub, tone }: { label: string; value: number; sub: string; tone?: "good" | "critical" }) {
  return (
    <div>
      <div className="text-[11px] font-medium text-muted">{label}</div>
      <div className={clsx("text-[22px] font-semibold tabnum leading-tight", tone === "good" && "text-good", tone === "critical" && "text-critical")}>
        {value.toFixed(1)} <span className="text-sm font-medium">days</span>
      </div>
      <div className="text-[11px] text-muted">{sub}</div>
    </div>
  );
}

/** Waterfall from declared remaining life down to the estimate, one step per contributing factor. */
export function Waterfall({ declaredRemaining, estimated, factors }: { declaredRemaining: number; estimated: number; factors: Factor[] }) {
  const scale = (v: number) => `${Math.max(0, (100 * v) / Math.max(declaredRemaining, 0.01))}%`;
  const steps = factors.filter((f) => f.days >= 0.01);
  let cursor = declaredRemaining;
  return (
    <div className="space-y-1.5">
      <Row label="Declared remaining" value={`${declaredRemaining.toFixed(1)} d`}>
        <div className="h-full rounded-sm bg-ink2/25" style={{ width: "100%" }} />
      </Row>
      {steps.map((f) => {
        const start = cursor - f.days;
        cursor = start;
        return (
          <Row key={f.key} label={f.label} value={`−${f.days.toFixed(1)} d`} valueClass="text-critical">
            <div className="h-full rounded-sm bg-critical/70" style={{ marginLeft: scale(start), width: scale(f.days) }} />
          </Row>
        );
      })}
      <Row label="Estimated usable" value={`${estimated.toFixed(1)} d`} valueClass="text-good" bold>
        <div className="h-full rounded-sm bg-good/70" style={{ width: scale(estimated) }} />
      </Row>
    </div>
  );
}

function Row({ label, value, children, valueClass, bold }: {
  label: string; value: string; children: React.ReactNode; valueClass?: string; bold?: boolean;
}) {
  return (
    <div className="grid grid-cols-[150px_1fr_64px] items-center gap-3">
      <div className={clsx("text-[12px] truncate", bold ? "font-semibold" : "text-ink2")}>{label}</div>
      <div className="h-4 w-full rounded-sm bg-line/40">{children}</div>
      <div className={clsx("text-[12px] font-semibold tabnum text-right", valueClass)}>{value}</div>
    </div>
  );
}

const LEVEL_TONE = { HIGH: "critical", MEDIUM: "warn", LOW: "neutral" } as const;

export function FactorList({ factors }: { factors: Factor[] }) {
  return (
    <ul className="divide-y divide-line">
      {factors.map((f) => (
        <li key={f.key} className="py-2 flex items-start gap-3">
          <div className="w-20 shrink-0"><Chip tone={LEVEL_TONE[f.level]}>{f.level}</Chip></div>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium flex justify-between gap-2">
              <span>{f.label}</span>
              <span className="tabnum text-ink2">{f.days > 0 ? `−${f.days.toFixed(2)} d` : "0 d"}{f.share_pct > 0 && <span className="text-muted"> · {f.share_pct.toFixed(0)}%</span>}</span>
            </div>
            <div className="text-[12px] text-muted">{f.evidence}</div>
          </div>
        </li>
      ))}
    </ul>
  );
}
