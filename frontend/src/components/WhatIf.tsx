import clsx from "clsx";
import { Ban, FlaskConical } from "lucide-react";
import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, fmt } from "../api";
import { Spinner } from "./ui";

interface Option {
  key: string; label: string; available: boolean; blocked_reason: string | null;
  expected_waste_kg?: number | null; expected_waste_pct?: number | null; revenue_qar?: number; social_value_qar?: number;
  delivery_hours?: number | null; remaining_at_destination_days?: number | null; quantity_saved_kg?: number | null;
  confidence?: number; lines?: any[]; note?: string;
}

const SHORT: Record<string, string> = {
  keep: "Do nothing (original route)", retailer_a: "Reroute → Retailer A", retailer_b: "Reroute → Retailer B",
  discount_10: "Discount 10%", discount_20: "Discount 20%", accelerate: "Accelerate delivery",
  rescue: "Send to rescue channel", optimized: "Q-Chain optimized split", hold: "Hold for review",
};

export default function WhatIf({ shipmentId, version }: { shipmentId: string; version: number }) {
  const [opts, setOpts] = useState<Option[] | null>(null);
  const [sel, setSel] = useState<string>("keep");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setOpts(null);
    api<{ options: Option[] }>(`/shipments/${shipmentId}/simulate`, { body: {} })
      .then((r) => { setOpts(r.options); setSel(r.options.find((o) => o.available)?.key ?? "keep"); })
      .catch((e) => setErr(e.message));
  }, [shipmentId, version]);

  if (err) return <div className="text-sm text-critical">{err}</div>;
  if (!opts) return <Spinner label="Simulating scenarios…" />;

  const avail = opts.filter((o) => o.available && o.expected_waste_pct != null);
  const chart = avail.map((o) => ({ key: o.key, name: SHORT[o.key] ?? o.label, waste: o.expected_waste_pct as number }));
  const best = avail.length ? avail.reduce((a, b) => ((a.expected_waste_pct ?? 1e9) <= (b.expected_waste_pct ?? 1e9) ? a : b)) : null;
  const current = opts.find((o) => o.key === sel);

  return (
    <div className="space-y-4">
      {avail.length > 0 && (
        <div className="grid lg:grid-cols-[1fr_1.1fr] gap-4">
          <div>
            <div className="text-[12px] font-medium text-ink2 mb-1">Expected waste by scenario (% of lot)</div>
            <div style={{ height: 36 * chart.length + 30 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chart} layout="vertical" margin={{ top: 0, right: 44, bottom: 0, left: 0 }} barCategoryGap={6}>
                  <CartesianGrid stroke="var(--c-grid)" horizontal={false} />
                  <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11, fill: "var(--c-axis)" }} tickFormatter={(v) => `${v}%`}
                    tickLine={false} axisLine={false} />
                  <YAxis type="category" dataKey="name" width={170} tick={{ fontSize: 12, fill: "rgb(var(--ink2))" }} tickLine={false} axisLine={false} />
                  <Tooltip cursor={{ fill: "rgb(var(--line) / .4)" }} formatter={(v) => [`${Number(v).toFixed(1)}%`, "Expected waste"]}
                    contentStyle={{ background: "rgb(var(--raised))", border: "1px solid rgb(var(--line))", borderRadius: 8, fontSize: 12 }} />
                  <Bar dataKey="waste" radius={[0, 4, 4, 0]} isAnimationActive={false} cursor="pointer"
                    onClick={(d: any) => d?.payload?.key && setSel(d.payload.key)}>
                    {chart.map((c) => (
                      <Cell key={c.key} fill={c.key === best?.key ? "rgb(var(--good))" : c.key === sel ? "var(--c-series-1)" : "rgb(var(--ink2) / .35)"} />
                    ))}
                    <LabelList dataKey="waste" position="right" formatter={(v: any) => `${Number(v).toFixed(0)}%`}
                      style={{ fontSize: 11, fill: "rgb(var(--ink2))" }} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="text-[11px] text-muted mt-1">Green = lowest expected waste. Click a bar to inspect it.</div>
          </div>
          {current && <Detail o={current} best={best?.key === current.key} />}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="border-b border-line">
            <tr>
              <th className="th">Scenario</th><th className="th text-right">Expected waste</th><th className="th text-right">Revenue</th>
              <th className="th text-right">Delivery</th><th className="th text-right">Life at destination</th>
              <th className="th text-right">Quantity saved</th><th className="th text-right">Confidence</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {opts.map((o) => (
              <tr key={o.key} onClick={() => o.available && setSel(o.key)}
                className={clsx(o.available ? "cursor-pointer hover:bg-page" : "opacity-60", sel === o.key && "bg-accent/[0.06]")}>
                <td className="td">
                  <div className="font-medium flex items-center gap-1.5">{!o.available && <Ban size={13} className="text-muted" />}{o.label}</div>
                  {!o.available && <div className="text-[11px] text-muted whitespace-normal">{o.blocked_reason}</div>}
                </td>
                <td className="td text-right tabnum">{o.expected_waste_pct != null ? `${o.expected_waste_pct.toFixed(1)}% · ${fmt.kg(o.expected_waste_kg)}` : "—"}</td>
                <td className="td text-right tabnum">{o.available ? fmt.qar(o.revenue_qar) : "—"}</td>
                <td className="td text-right tabnum">{o.delivery_hours != null ? `${o.delivery_hours} h` : "—"}</td>
                <td className="td text-right tabnum">{o.remaining_at_destination_days != null ? `${o.remaining_at_destination_days.toFixed(1)} d` : "—"}</td>
                <td className="td text-right tabnum">{fmt.kg(o.quantity_saved_kg)}</td>
                <td className="td text-right tabnum">{o.confidence != null && o.available ? fmt.pct(o.confidence * 100) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center gap-1.5 text-[11px] text-muted"><FlaskConical size={12} />
        Prototype calculations on the synthetic demo dataset. Buyers accept lots on the declared date; sales depend on the estimated usable window.</div>
    </div>
  );
}

function Detail({ o, best }: { o: Option; best: boolean }) {
  return (
    <div className="rounded-xl border border-line bg-raised p-4">
      <div className="flex items-center gap-2">
        <div className="font-semibold">{o.label}</div>
        {best && <span className="chip bg-good/15 text-good">lowest waste</span>}
      </div>
      <div className="mt-3 grid grid-cols-3 gap-3">
        <M label="Expected waste" v={o.expected_waste_pct != null ? `${o.expected_waste_pct.toFixed(0)}%` : "—"} />
        <M label="Revenue" v={fmt.qar(o.revenue_qar)} />
        <M label="Saved" v={fmt.kg(o.quantity_saved_kg)} />
      </div>
      <ul className="mt-3 space-y-1.5">
        {(o.lines ?? []).map((l: any) => (
          <li key={l.destination_id} className="text-[12px] text-ink2">
            <span className="font-semibold text-ink tabnum">{Math.round(l.qty_kg)} kg</span> → {l.destination}
            <span className="tabnum"> · {Math.round(l.sold_kg)} kg used · {l.remaining_at_arrival_days.toFixed(1)} d window on arrival</span>
            <div className="text-muted">{l.reason}</div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function M({ label, v }: { label: string; v: string }) {
  return (
    <div>
      <div className="text-[11px] text-muted">{label}</div>
      <div className="text-lg font-semibold tabnum">{v}</div>
    </div>
  );
}
