import clsx from "clsx";
import { ArrowRight, Check, CircleCheck, HeartHandshake, LifeBuoy, LoaderCircle, ShieldAlert, Store, Tag } from "lucide-react";
import { useEffect, useState } from "react";
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip } from "react-leaflet";
import { useDark } from "../App";
import { api, fmt } from "../api";
import { Chip, Note } from "./ui";

export interface PlanLine {
  destination_id: string; destination: string; kind: string; type: string; channel: "sale" | "discount" | "rescue";
  location_name: string; lat: number; lon: number; qty_kg: number; sold_kg: number; waste_kg: number;
  revenue_qar: number; social_value_qar: number; arrival_hours: number; remaining_at_arrival_days: number; reason: string;
  accepted: boolean;
}
export interface Plan {
  lines: PlanLine[]; unallocated_kg: number; total_qty_kg: number; used_kg: number; expected_waste_kg: number | null;
  expected_waste_pct: number | null; revenue_qar: number; social_value_qar: number; transport_qar: number;
}
export interface Recommendation {
  current_route: Plan | null; optimized: Plan; food_saved_kg: number; revenue_recovered_qar: number;
  social_value_qar: number; waste_avoided_kg: number; affected_qty_kg: number | null; action_label: string;
  candidates: any[]; note: string;
}

const CHANNEL: Record<string, { label: string; icon: React.ReactNode; tone: string }> = {
  sale: { label: "Priority sale", icon: <Store size={12} />, tone: "accent" },
  discount: { label: "Rapid discounted sale", icon: <Tag size={12} />, tone: "warn" },
  rescue: { label: "Food-rescue review", icon: <HeartHandshake size={12} />, tone: "good" },
};

export default function SaveShipment({ shipmentId, canOperate, origin, onDone, qty }: {
  shipmentId: string; canOperate: boolean; origin: { lat: number; lon: number } | null; qty: number;
  onDone?: () => void;
}) {
  const [res, setRes] = useState<any>(null);
  const [shown, setShown] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [accepted, setAccepted] = useState<string | null>(null);

  async function run() {
    setBusy(true); setErr(null); setRes(null); setShown(0); setAccepted(null);
    try {
      const r = await api(`/shipments/${shipmentId}/optimize`, { method: "POST" });
      setRes(r);
      onDone?.();
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  useEffect(() => {
    if (!res || shown >= res.steps.length + 1) return;
    const t = setTimeout(() => setShown((s) => s + 1), 420);
    return () => clearTimeout(t);
  }, [res, shown]);

  async function accept() {
    const r = await api(`/shipments/${shipmentId}/recommendation/accept`, { method: "POST" });
    setAccepted(`Plan accepted by ${r.accepted_by} at ${fmt.dt(r.accepted_at)} — logged to the audit trail.`);
  }

  const done = res && shown > res.steps.length;
  const rec: Recommendation | undefined = res?.recommendation;
  const hold = res?.analysis?.classification === "HOLD";

  return (
    <div>
      {!res && (
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
          <button onClick={run} disabled={busy || !canOperate}
            className="btn bg-good text-white hover:brightness-110 !px-6 !py-3 text-base font-semibold shadow-sm">
            {busy ? <LoaderCircle size={18} className="animate-spin" /> : <LifeBuoy size={18} />}
            SAVE THIS SHIPMENT
          </button>
          <div className="text-sm text-ink2 max-w-xl">
            Analyse the condition, estimate usable life, find the affected quantity, simulate alternative routes and
            recommend the lowest-waste <strong>compliant</strong> action.
            {!canOperate && <div className="text-[12px] text-muted mt-1">Your role is read-only — ask a warehouse manager or distributor.</div>}
          </div>
        </div>
      )}
      {err && <div className="text-sm text-critical mt-2">{err}</div>}

      {res && (
        <ol className="grid sm:grid-cols-2 xl:grid-cols-4 gap-2 mb-4">
          {res.steps.map((s: any, i: number) => (
            <li key={s.step} className={clsx("rounded-lg border px-3 py-2 transition-all duration-300",
              i < shown ? "border-line bg-raised opacity-100" : "border-dashed border-line opacity-40")}>
              <div className="flex items-center gap-2 text-[12px] font-semibold">
                {i < shown ? <CircleCheck size={14} className="text-good" /> : <LoaderCircle size={14} className="animate-spin text-muted" />}
                {s.step}. {s.title}
              </div>
              {i < shown && <div className="text-[12px] text-ink2 mt-0.5 fade-up">{s.detail}</div>}
            </li>
          ))}
        </ol>
      )}

      {done && rec && hold && (
        <div className="rounded-lg border border-hold/40 bg-hold/[0.06] p-4 flex gap-3 fade-up">
          <ShieldAlert className="text-hold shrink-0" />
          <div>
            <div className="font-semibold">HOLD — do not sell or donate</div>
            <div className="text-sm text-ink2">This shipment triggered a compliance rule. It is flagged for inspection /
              compliance / disposal workflow. Q-Chain does not simulate sale or redistribution while a hold is active.</div>
          </div>
        </div>
      )}

      {done && rec && !hold && (
        <div className="space-y-4 fade-up">
          <div className="grid md:grid-cols-[1fr_auto_1fr] items-stretch gap-3">
            <RouteCard title="Current route" subtitle={rec.current_route?.lines[0]?.destination ?? "—"} plan={rec.current_route} tone="critical" />
            <div className="hidden md:flex items-center justify-center text-muted"><ArrowRight /></div>
            <RouteCard title="Q-Chain optimized" subtitle={rec.action_label} plan={rec.optimized} tone="good" />
          </div>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Big label="Potential food saved" value={fmt.kg(rec.food_saved_kg)} tone="good" />
            <Big label="Revenue recovered" value={fmt.qar(rec.revenue_recovered_qar)} tone="accent" />
            <Big label="Potential waste avoided" value={fmt.kg(rec.waste_avoided_kg)} tone="good" />
            <Big label="Social value (rescue)" value={fmt.qar(rec.social_value_qar)} />
          </div>

          <div className="grid xl:grid-cols-[1.3fr_1fr] gap-4">
            <div>
              <div className="card-t mb-2">Recommended allocation</div>
              <ul className="space-y-2">
                {rec.optimized.lines.map((l) => (
                  <li key={l.destination_id} className="rounded-lg border border-line bg-raised p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-lg font-semibold tabnum">{Math.round(l.qty_kg)} kg</span>
                      <ArrowRight size={15} className="text-muted" />
                      <span className="font-medium">{l.destination}</span>
                      <Chip tone={CHANNEL[l.channel].tone} icon={CHANNEL[l.channel].icon}>{CHANNEL[l.channel].label}</Chip>
                    </div>
                    <div className="mt-1 grid grid-cols-2 sm:grid-cols-4 gap-2 text-[12px] text-ink2 tabnum">
                      <span>Expected used: <strong>{Math.round(l.sold_kg)} kg</strong></span>
                      <span>Arrives in {l.arrival_hours.toFixed(1)} h</span>
                      <span>{l.remaining_at_arrival_days.toFixed(1)} d window on arrival</span>
                      <span>{l.channel === "rescue" ? fmt.qar(l.social_value_qar) + " social" : fmt.qar(l.revenue_qar)}</span>
                    </div>
                    <div className="mt-1 text-[12px] text-muted">{l.reason}</div>
                  </li>
                ))}
                {rec.optimized.unallocated_kg > 0 && (
                  <li className="rounded-lg border border-dashed border-line p-3 text-sm text-ink2">
                    {Math.round(rec.optimized.unallocated_kg)} kg without an eligible destination → inspection / disposal review.
                  </li>
                )}
              </ul>
            </div>
            <AllocationMap origin={origin} lines={rec.optimized.lines} />
          </div>

          <details className="rounded-lg border border-line">
            <summary className="cursor-pointer px-3 py-2 text-sm font-medium">All {rec.candidates.length} candidate destinations considered</summary>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="border-y border-line"><tr>
                  <th className="th">Destination</th><th className="th">Channel</th><th className="th text-right">Demand/day</th>
                  <th className="th text-right">On hand</th><th className="th text-right">Delivery</th>
                  <th className="th text-right">Window on arrival</th><th className="th">Eligibility</th></tr></thead>
                <tbody className="divide-y divide-line">
                  {rec.candidates.map((c) => (
                    <tr key={c.id}>
                      <td className="td">{c.name}{c.is_original && <span className="ml-1 text-[11px] text-muted">(original)</span>}</td>
                      <td className="td">{c.channel}</td>
                      <td className="td text-right tabnum">{c.daily_kg != null ? `${c.daily_kg} kg` : `${c.max_kg} kg cap.`}</td>
                      <td className="td text-right tabnum">{c.inventory_kg != null ? `${Math.round(c.inventory_kg)} kg` : "—"}</td>
                      <td className="td text-right tabnum">{c.hours} h</td>
                      <td className="td text-right tabnum">{c.remaining_at_arrival_days.toFixed(1)} d</td>
                      <td className="td">{c.eligible ? <Chip tone="good">eligible</Chip> : <span className="text-[12px] text-muted">{c.ineligible_reason}</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>

          <div className="flex flex-wrap items-center gap-3">
            {canOperate && !accepted && <button className="btn-primary" onClick={accept}><Check size={16} /> Accept plan</button>}
            {accepted && <span className="text-sm text-good flex items-center gap-1.5"><CircleCheck size={16} /> {accepted}</span>}
            <button className="btn-ghost" onClick={run}>Re-run</button>
            <Note>{res.note} Rescue lines are "eligible for food-rescue review, subject to applicable food-safety and organizational acceptance requirements." Total {Math.round(qty)} kg.</Note>
          </div>
        </div>
      )}
    </div>
  );
}

function RouteCard({ title, subtitle, plan, tone }: { title: string; subtitle: string; plan: Plan | null; tone: "good" | "critical" }) {
  return (
    <div className={clsx("rounded-xl border p-4", tone === "good" ? "border-good/40 bg-good/[0.05]" : "border-critical/30 bg-critical/[0.04]")}>
      <div className="text-[12px] font-semibold uppercase tracking-wide text-muted">{title}</div>
      <div className="text-sm font-medium truncate">{subtitle}</div>
      <div className="mt-2 flex items-end gap-2">
        <span className={clsx("text-4xl font-semibold tabnum", tone === "good" ? "text-good" : "text-critical")}>
          {plan?.expected_waste_pct != null ? `${plan.expected_waste_pct.toFixed(0)}%` : "—"}
        </span>
        <span className="text-sm text-ink2 pb-1">expected waste</span>
      </div>
      <div className="text-[12px] text-muted tabnum">
        {plan ? `${fmt.kg(plan.expected_waste_kg)} wasted · ${fmt.qar(plan.revenue_qar)} revenue` : ""}
      </div>
    </div>
  );
}

function Big({ label, value, tone }: { label: string; value: string; tone?: "good" | "accent" }) {
  return (
    <div className="rounded-lg border border-line bg-raised px-3 py-2.5">
      <div className="text-[11px] font-medium text-muted">{label}</div>
      <div className={clsx("text-xl font-semibold tabnum", tone === "good" && "text-good", tone === "accent" && "text-accent")}>{value}</div>
    </div>
  );
}

function AllocationMap({ origin, lines }: { origin: { lat: number; lon: number } | null; lines: PlanLine[] }) {
  const dark = useDark();
  if (!origin) return null;
  const color = { sale: dark ? "#3987e5" : "#2a78d6", discount: dark ? "#fab219" : "#d69600", rescue: "#0ca30c" };
  return (
    <div className="h-[300px] rounded-lg overflow-hidden border border-line">
      <MapContainer center={[origin.lat, origin.lon]} zoom={10} scrollWheelZoom={false} style={{ height: "100%" }}>
        <TileLayer key={dark ? "d" : "l"}
          url={dark ? "https://tile.openstreetmap.org/{z}/{x}/{y}.png" : "https://tile.openstreetmap.org/{z}/{x}/{y}.png"}
          attribution='&copy; OpenStreetMap contributors' />
        {lines.map((l) => (
          <Polyline key={l.destination_id} positions={[[origin.lat, origin.lon], [l.lat, l.lon]]}
            pathOptions={{ color: color[l.channel], weight: 2 + Math.min(6, l.qty_kg / 80) }} />
        ))}
        {lines.map((l) => (
          <CircleMarker key={`m${l.destination_id}`} center={[l.lat, l.lon]} radius={7}
            pathOptions={{ color: "#fff", weight: 2, fillColor: color[l.channel], fillOpacity: 1 }}>
            <Tooltip permanent direction="top" offset={[0, -6]}>{Math.round(l.qty_kg)} kg · {l.location_name}</Tooltip>
          </CircleMarker>
        ))}
        <CircleMarker center={[origin.lat, origin.lon]} radius={8} pathOptions={{ color: "#fff", weight: 2, fillColor: "#d03b3b", fillOpacity: 1 }}>
          <Tooltip direction="bottom">Shipment now</Tooltip>
        </CircleMarker>
      </MapContainer>
    </div>
  );
}
