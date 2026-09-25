import clsx from "clsx";
import { CircleCheck, FlaskConical, Info, LoaderCircle, OctagonAlert, ShieldAlert, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { CLASS_META, type Classification } from "../api";

const TONE: Record<string, string> = {
  good: "bg-good/12 text-good ring-good/30",
  warn: "bg-warn/15 text-[rgb(var(--warn))] ring-warn/40",
  serious: "bg-serious/15 text-serious ring-serious/40",
  critical: "bg-critical/12 text-critical ring-critical/30",
  hold: "bg-hold/15 text-hold ring-hold/40",
  neutral: "bg-line/60 text-ink2 ring-line",
  accent: "bg-accent/12 text-accent ring-accent/30",
};

export function Chip({ tone = "neutral", children, icon }: { tone?: string; children: ReactNode; icon?: ReactNode }) {
  return <span className={clsx("chip ring-1 ring-inset", TONE[tone])}>{icon}{children}</span>;
}

const CLASS_ICON: Record<Classification, ReactNode> = {
  GOOD: <CircleCheck size={12} />,
  MID: <TriangleAlert size={12} />,
  LOW: <OctagonAlert size={12} />,
  HOLD: <ShieldAlert size={12} />,
};

/** Status never relies on color alone: icon + label always accompany the hue. */
export function ClassBadge({ c, withAction = false }: { c: Classification | null | undefined; withAction?: boolean }) {
  if (!c) return <Chip>—</Chip>;
  const m = CLASS_META[c];
  return (
    <Chip tone={m.tone} icon={CLASS_ICON[c]}>
      {m.short}{withAction ? ` · ${m.action}` : ""}
    </Chip>
  );
}

const RISK_TONE: Record<string, string> = { LOW: "good", MEDIUM: "warn", HIGH: "serious", CRITICAL: "hold" };
export function RiskBadge({ r }: { r: string | null | undefined }) {
  if (!r) return <Chip>—</Chip>;
  return <Chip tone={RISK_TONE[r]}>{r}</Chip>;
}

export function Card({ title, right, children, className, bodyClass }: {
  title?: ReactNode; right?: ReactNode; children: ReactNode; className?: string; bodyClass?: string;
}) {
  return (
    <section className={clsx("card", className)}>
      {(title || right) && (
        <div className="card-h">
          {title ? <h2 className="card-t">{title}</h2> : <span />}
          {right}
        </div>
      )}
      <div className={clsx("px-4 pb-4", !title && !right && "pt-4", bodyClass)}>{children}</div>
    </section>
  );
}

export function Kpi({ label, value, sub, tone, icon }: {
  label: string; value: ReactNode; sub?: ReactNode; tone?: "good" | "warn" | "critical" | "accent"; icon?: ReactNode;
}) {
  return (
    <div className="card px-4 py-3.5 min-w-0">
      <div className="flex items-center justify-between gap-2 text-[12px] font-medium text-ink2">
        <span className="truncate">{label}</span>
        <span className={clsx(tone === "good" && "text-good", tone === "warn" && "text-[rgb(var(--warn))]",
          tone === "critical" && "text-critical", tone === "accent" && "text-accent", !tone && "text-muted")}>{icon}</span>
      </div>
      <div className="mt-1.5 text-[26px] leading-tight font-semibold tracking-tight">{value}</div>
      {sub && <div className="mt-0.5 text-[12px] text-muted">{sub}</div>}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-muted p-6">
      <LoaderCircle size={16} className="animate-spin" /> {label ?? "Loading…"}
    </div>
  );
}

export function SimNotice({ text, compact }: { text: string; compact?: boolean }) {
  return (
    <div className={clsx("flex items-start gap-2 rounded-lg border border-dashed border-line text-muted",
      compact ? "px-2.5 py-1.5 text-[11px]" : "px-3 py-2 text-[12px]")}>
      <FlaskConical size={compact ? 12 : 14} className="mt-0.5 shrink-0" />
      <span>{text}</span>
    </div>
  );
}

export function Note({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-2 text-[12px] text-muted">
      <Info size={13} className="mt-0.5 shrink-0" />
      <span>{children}</span>
    </div>
  );
}

export function Confidence({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2" title="Prediction confidence (heuristic: model interval, physics/ML agreement, data quality)">
      <div className="h-1.5 w-20 rounded-full bg-line overflow-hidden">
        <div className="h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-sm font-medium tabnum">{pct}%</span>
    </div>
  );
}

export function ErrorBox({ error }: { error: unknown }) {
  return (
    <div className="card p-4 text-sm text-critical flex items-center gap-2">
      <TriangleAlert size={16} /> {error instanceof Error ? error.message : String(error)}
    </div>
  );
}
