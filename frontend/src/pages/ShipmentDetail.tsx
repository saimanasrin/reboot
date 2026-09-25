import clsx from "clsx";
import {
  ArrowLeft, Bot, CircleCheck, Database, ExternalLink, Factory, Gauge, LifeBuoy, Plane, RefreshCw, Scale, Ship,
  ShieldAlert, ShieldCheck, Snowflake, Split, Store, Truck, Warehouse,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useUser } from "../App";
import { api, canOperate, fmt } from "../api";
import AgentPanel from "../components/AgentPanel";
import SaveShipment, { type Recommendation } from "../components/SaveShipment";
import { SensorTimeline, type History, type JourneySeg } from "../components/SensorCharts";
import { FactorList, ShelfLifeTimeline, Waterfall } from "../components/ShelfLife";
import { Card, Chip, ClassBadge, Confidence, ErrorBox, Note, RiskBadge, SimNotice, Spinner } from "../components/ui";
import WhatIf from "../components/WhatIf";

const STAGE_ICON: Record<string, React.ReactNode> = {
  origin: <Factory size={16} />, transport: <Plane size={16} />, port: <Ship size={16} />,
  cold_storage: <Warehouse size={16} />, distribution: <Truck size={16} />,
};
const STAGE_LABEL: Record<string, string> = {
  origin: "Origin", transport: "Transport", port: "Port / airport", cold_storage: "Cold storage", distribution: "Distribution",
};

export default function ShipmentDetail() {
  const { id = "" } = useParams();
  const user = useUser();
  const [d, setD] = useState<any>(null);
  const [h, setH] = useState<History | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api(`/shipments/${id}`).then(setD).catch(setErr);
    api<History>(`/shipments/${id}/sensor-history`).then(setH).catch(setErr);
  }, [id]);
  useEffect(() => { setD(null); setH(null); load(); }, [load]);

  if (err) return <div className="p-6"><ErrorBox error={err} /></div>;
  if (!d) return <Spinner label={`Loading ${id}…`} />;

  const s = d.shipment, a = d.analysis, p = d.product;
  const rec: Recommendation | null = a.recommendation;
  const ex = a.explanation;
  const hold = a.classification === "HOLD";

  async function rerun() {
    setBusy(true);
    try { await api(`/shipments/${id}/predict`, { method: "POST" }); load(); setVersion((v) => v + 1); }
    finally { setBusy(false); }
  }

  return (
    <div className="p-4 md:p-6 space-y-4 max-w-[1600px] mx-auto">
      <Link to="/" className="inline-flex items-center gap-1 text-[13px] text-muted hover:text-ink"><ArrowLeft size={14} /> Command centre</Link>

      {/* 1. What needs attention */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl md:text-[28px] font-semibold tracking-tight">Shipment {s.shipment_id}</h1>
            <ClassBadge c={a.classification} withAction />
            <RiskBadge r={a.risk_level} />
            <Chip tone="neutral">{a.label}</Chip>
          </div>
          <div className="mt-1 text-sm text-ink2">
            {s.product_name} · <span className="tabnum">{fmt.kg(s.quantity_kg)}</span> · {s.transport_mode} import ·
            device {s.device_id} · now at <strong>{s.current_location}</strong>
          </div>
        </div>
        <div className="flex gap-2">
          <button className="btn-ghost" onClick={rerun} disabled={busy}><RefreshCw size={15} className={clsx(busy && "animate-spin")} /> Re-run prediction</button>
          <a href="#save" className="btn bg-good text-white hover:brightness-110 font-semibold"><LifeBuoy size={16} /> Save this shipment</a>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <div className="card p-4 col-span-2 lg:col-span-1">
          <div className="text-[12px] font-medium text-ink2">Estimated usable quality window</div>
          <div className="text-[34px] font-semibold tabnum leading-tight">{fmt.d(a.estimated_remaining_days)} <span className="text-base font-medium">days</span></div>
          <div className="text-[12px] text-muted tabnum">vs {fmt.d(a.declared_remaining_days)} d declared remaining · −{fmt.d(a.loss_days)} d</div>
        </div>
        <Mini label="Production date" value={fmt.date(s.production_date)} sub={`${fmt.d(a.elapsed_days)} d elapsed`} />
        <Mini label="Declared expiry (unchanged)" value={fmt.date(s.declared_expiry)} sub={`${p.declared_shelf_life_days} d declared shelf life`} />
        <div className="card p-4">
          <div className="text-[12px] font-medium text-ink2 mb-1.5">Prediction confidence</div>
          <Confidence value={a.confidence} />
          <div className="text-[11px] text-muted mt-1.5 tabnum">range {a.estimated_range_days[0]}–{a.estimated_range_days[1]} d</div>
        </div>
        <div className="card p-4">
          <div className="text-[12px] font-medium text-ink2">Compliance</div>
          <div className={clsx("mt-1 flex items-center gap-1.5 font-semibold",
            a.compliance.status === "HOLD" ? "text-hold" : a.compliance.status === "CONDITIONAL" ? "text-[rgb(var(--warn))]" : "text-good")}>
            {a.compliance.status === "CLEAR" ? <ShieldCheck size={16} /> : <ShieldAlert size={16} />} {a.compliance.status}
          </div>
          <div className="text-[11px] text-muted mt-0.5">{a.compliance.triggered_rules.length} rule(s) triggered</div>
        </div>
      </div>

      {/* Journey */}
      <Card title="Journey reconstruction">
        <ol className="flex flex-wrap lg:flex-nowrap items-stretch gap-2">
          {d.journey.map((j: JourneySeg & { hours: number }, i: number) => {
            const exc = ex.episodes.some((e: any) => e.start < (j.end_ts ?? "9") && e.end > j.start_ts);
            return (
              <li key={j.seq} className="flex items-center gap-2 flex-1 min-w-[160px]">
                <div className={clsx("flex-1 rounded-lg border p-2.5", exc ? "border-critical/50 bg-critical/[0.05]" : "border-line bg-raised")}>
                  <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted">
                    {STAGE_ICON[j.stage]} {STAGE_LABEL[j.stage]}
                  </div>
                  <div className="text-[13px] font-medium leading-snug mt-0.5">{j.label}</div>
                  <div className="text-[11px] text-muted tabnum">{fmt.dt(j.start_ts)} · {j.hours} h</div>
                  {exc && <div className="text-[11px] font-semibold text-critical mt-0.5">Excursion during this stage</div>}
                </div>
                {i < d.journey.length - 1 && <span className="hidden lg:block text-muted">›</span>}
              </li>
            );
          })}
        </ol>
      </Card>

      <div className="grid 2xl:grid-cols-[1.6fr_1fr] gap-4">
        <Card title="Sensor timeline" right={<Chip tone="neutral">{h?.label ?? "SYNTHETIC"}</Chip>}>
          {h ? <SensorTimeline h={h} episodes={ex.episodes} journey={d.journey} /> : <Spinner />}
          {h && <div className="mt-3"><SimNotice text={h.disclaimer} compact /></div>}
        </Card>
        <div className="grid lg:grid-cols-2 2xl:grid-cols-1 gap-4 content-start">
          <Card title="Shelf-life analysis">
            <ShelfLifeTimeline declared={ex.timeline.declared_total_days} elapsed={ex.timeline.elapsed_days}
              lost={ex.timeline.lost_days} usable={ex.timeline.estimated_remaining_days} range={a.estimated_range_days} />
            <div className="mt-3 grid grid-cols-3 gap-2 text-[12px]">
              <Kv k="Physics layer" v={`−${fmt.d(a.physics_loss_days, 2)} d`} />
              <Kv k="ML layer" v={`−${fmt.d(a.ml_loss_days, 2)} d`} />
              <Kv k="Deterioration score" v={`${fmt.d(a.deterioration_score, 0)}/100`} />
            </div>
            <div className="mt-2"><Note>Blend: 60% physics-inspired model + 40% gradient-boosting model ({a.model_version}). Prototype — not validated against measured food quality.</Note></div>
          </Card>
          <DataQualityCard q={a.data_quality} />
        </div>
      </div>

      {/* 2. Why */}
      <Card title={<span className="flex items-center gap-2"><Gauge size={14} /> Why did the shelf life drop?</span>}>
        <p className="text-[15px] leading-relaxed max-w-4xl">{ex.summary}</p>
        <div className="mt-4 grid lg:grid-cols-2 gap-6">
          <div>
            <div className="card-t mb-2">Contribution to lost usable life</div>
            <Waterfall declaredRemaining={a.declared_remaining_days} estimated={a.estimated_remaining_days} factors={ex.factors} />
          </div>
          <div>
            <div className="card-t mb-1">Contributing factors</div>
            <FactorList factors={ex.factors} />
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted">
          {ex.citations.map((c: any) => <span key={c.ref}><code className="rounded bg-line/60 px-1">{c.ref}</code> {c.text}</span>)}
        </div>
        <div className="mt-2"><Note>{ex.disclaimer}</Note></div>
      </Card>

      {/* 3. What should I do */}
      <Card title={<span id="save" className="flex items-center gap-2"><LifeBuoy size={14} /> What should happen next?</span>}
        right={rec && <span className="text-sm font-semibold">{hold ? "Hold for review" : rec.action_label}</span>}>
        {rec && !hold && (
          <div className="mb-4 text-sm text-ink2">
            Classification <strong>{a.classification}</strong> ({a.action}) —{" "}
            {a.classification === "GOOD" ? "enough usable life for normal distribution." :
              a.classification === "MID" ? "usable life is declining; prioritise faster-moving customers." :
                "short window; use rapid-sale / direct channels or eligible rescue channels."}
            {d.analysis.recommendation_status === "accepted" &&
              <span className="ml-2 text-good inline-flex items-center gap-1"><CircleCheck size={14} /> plan accepted by {d.analysis.recommendation_accepted_by}</span>}
          </div>
        )}
        <SaveShipment shipmentId={s.shipment_id} canOperate={canOperate(user)} qty={s.quantity_kg}
          origin={s.current_lat ? { lat: s.current_lat, lon: s.current_lon } : null} onDone={() => setVersion((v) => v + 1)} />
      </Card>

      {/* 4. What if I don't */}
      <Card title={<span className="flex items-center gap-2"><Split size={14} /> What if? — alternative scenarios</span>}>
        <WhatIf shipmentId={s.shipment_id} version={version} />
      </Card>

      <div className="grid xl:grid-cols-2 gap-4">
        <Card title={<span className="flex items-center gap-2"><Bot size={14} /> Ask Q-Chain</span>}>
          <AgentPanel shipmentId={s.shipment_id} />
        </Card>
        <CompliancePanel c={a.compliance} />
      </div>

      <div className="grid xl:grid-cols-2 gap-4">
        <ProductCard p={p} customer={s.original_customer} />
        <Card title="Alerts for this shipment" bodyClass="!px-0">
          {d.alerts.length === 0 ? <div className="px-4 text-sm text-muted">No alerts.</div> : (
            <ul className="divide-y divide-line">
              {d.alerts.map((al: any, i: number) => (
                <li key={i} className="px-4 py-2 text-sm">
                  <span className="text-[11px] font-semibold uppercase text-muted mr-2">{al.kind.replace("_", " ")}</span>
                  {al.message} <span className="text-[11px] text-muted">· {fmt.dt(al.ts)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}

function Mini({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="card p-4">
      <div className="text-[12px] font-medium text-ink2">{label}</div>
      <div className="text-lg font-semibold mt-0.5">{value}</div>
      <div className="text-[11px] text-muted">{sub}</div>
    </div>
  );
}

function Kv({ k, v }: { k: string; v: string }) {
  return <div className="rounded-lg bg-page px-2.5 py-1.5"><div className="text-muted text-[11px]">{k}</div><div className="font-semibold tabnum">{v}</div></div>;
}

function DataQualityCard({ q }: { q: any }) {
  const tone = q.score >= 90 ? "text-good" : q.score >= 75 ? "text-[rgb(var(--warn))]" : "text-critical";
  return (
    <Card title={<span className="flex items-center gap-2"><Database size={14} /> Data quality</span>}>
      <div className="flex items-end gap-4">
        <div className={clsx("text-[34px] font-semibold tabnum leading-none", tone)}>{q.score.toFixed(0)}%</div>
        <div className="grid grid-cols-3 gap-3 text-[12px] flex-1">
          <div><div className="text-muted">Connectivity</div><div className="font-semibold">{q.connectivity}</div></div>
          <div><div className="text-muted">Missing readings</div><div className="font-semibold tabnum">{q.missing_pct}%</div></div>
          <div><div className="text-muted">Valid readings</div><div className="font-semibold tabnum">{q.valid_readings}</div></div>
        </div>
      </div>
      <ul className="mt-3 text-[12px] text-ink2 space-y-0.5">
        {q.issues.length === 0 ? <li>No issues detected.</li> : q.issues.map((i: string) => <li key={i}>• {i}</li>)}
      </ul>
      <div className="mt-2 text-[11px] text-muted">Checks: missing readings, outliers, impossible values, duplicate timestamps, disconnects, stale GPS, battery, product info.</div>
    </Card>
  );
}

function CompliancePanel({ c }: { c: any }) {
  const el = c.eligibility;
  return (
    <Card title={<span className="flex items-center gap-2"><Scale size={14} /> Compliance & eligibility</span>}
      right={<Chip tone={c.status === "HOLD" ? "hold" : c.status === "CONDITIONAL" ? "warn" : "good"}>{c.status}</Chip>}>
      <div className="grid grid-cols-3 gap-2 mb-3">
        {[["Normal sale", el.normal_sale], ["Discounted sale", el.discount_sale], ["Rescue review", el.rescue_review]].map(([k, v]) => (
          <div key={k as string} className={clsx("rounded-lg border px-3 py-2 text-[12px] font-medium flex items-center gap-1.5",
            v ? "border-good/40 text-good" : "border-line text-muted")}>
            {v ? <CircleCheck size={14} /> : <ShieldAlert size={14} />} {k as string}
          </div>
        ))}
      </div>
      <div className="text-[12px] text-ink2 mb-2">Official reference: {c.official_threshold} · {c.official_breach_hours} h beyond it</div>
      <ul className="space-y-2">
        {c.triggered_rules.length === 0 && <li className="text-sm text-muted">No rules triggered.</li>}
        {c.triggered_rules.map((r: any, i: number) => (
          <li key={i} className="rounded-lg border border-line p-2.5">
            <div className="flex flex-wrap items-center gap-2 text-sm font-medium">
              <code className="text-[11px] text-muted">{r.rule_id}</code> {r.name}
              <Chip tone={r.rule_type === "official_threshold" ? "accent" : "neutral"}>
                {r.rule_type === "official_threshold" ? "Official threshold (MOPH)" : "Prototype policy"}
              </Chip>
              <Chip tone={r.outcome === "HOLD" ? "hold" : "warn"}>{r.outcome}</Chip>
            </div>
            <div className="text-[12px] text-ink2 mt-0.5">{r.detail}</div>
            {r.source.startsWith("http") && (
              <a href={r.source} target="_blank" rel="noreferrer" className="text-[11px] text-accent inline-flex items-center gap-1 mt-0.5">
                Source <ExternalLink size={10} />
              </a>
            )}
          </li>
        ))}
      </ul>
      {c.rescue_statement && <div className="mt-3 text-[12px] text-ink2 rounded-lg bg-good/[0.07] px-3 py-2">{c.rescue_statement}</div>}
      <div className="mt-2"><Note>{c.statement}</Note></div>
    </Card>
  );
}

function ProductCard({ p, customer }: { p: any; customer: string | null }) {
  return (
    <Card title={<span className="flex items-center gap-2"><Snowflake size={14} /> Product & storage requirements</span>}>
      <div className="grid sm:grid-cols-2 gap-4 text-[13px]">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wide text-accent mb-1">Official regulatory threshold</div>
          <div className="font-medium">{p.official_threshold.label}</div>
          <div className="text-[11px] text-muted">Qatar MOPH guidance</div>
          <div className="mt-3 text-[11px] font-semibold uppercase tracking-wide text-muted mb-1 flex items-center gap-1"><Store size={12} /> Original customer</div>
          <div>{customer ?? "—"}</div>
        </div>
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted mb-1">Demo product parameters (prototype)</div>
          <dl className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[12px]">
            <dt className="text-muted">Target band</dt><dd className="tabnum">{p.required_min_temperature}–{p.required_max_temperature} °C</dd>
            <dt className="text-muted">Humidity</dt><dd className="tabnum">{p.humidity_min ? `${p.humidity_min}–${p.humidity_max}%` : "—"}</dd>
            <dt className="text-muted">Declared shelf life</dt><dd className="tabnum">{p.declared_shelf_life_days} d</dd>
            <dt className="text-muted">Sensitivity</dt><dd>{p.sensitivity} (Q10 {p.q10})</dd>
            <dt className="text-muted">Min. usable window</dt><dd className="tabnum">{p.min_window_days} d</dd>
            <dt className="text-muted">High-risk</dt><dd>{p.high_risk ? "yes" : "no"}</dd>
          </dl>
        </div>
      </div>
      <div className="mt-3 text-[12px] text-ink2">{p.notes}</div>
      <div className="mt-2"><Note>Demo parameters are illustrative, not legal shelf-life rules, and kept separate from official thresholds.</Note></div>
    </Card>
  );
}
