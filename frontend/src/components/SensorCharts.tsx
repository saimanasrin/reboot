import clsx from "clsx";
import { DoorOpen, Pause, Play, RotateCcw, ThermometerSun, Zap } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Area, CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis,
} from "recharts";
import { fmt } from "../api";

export interface Reading {
  ts: string; temperature_c: number | null; humidity_pct: number | null; lat: number | null; lon: number | null;
  door_open: boolean; motion: string; battery_pct: number | null; flag: string | null; out_of_band: boolean;
}
export interface History {
  band: { min_c: number | null; max_c: number; ref_c: number };
  humidity_band: { min: number | null; max: number | null };
  official_threshold: { min_c: number | null; max_c: number; label: string };
  readings: Reading[];
  label: string;
  disclaimer: string;
}
export interface Episode { kind: string; start: string; end: string; duration_h: number; peak_c: number; location: string; limit_c: number }
export interface JourneySeg { seq: number; stage: string; segment_type: string; label: string; location_name: string; start_ts: string; end_ts: string | null; hours: number | null }

const AXIS = { fontSize: 11, fill: "var(--c-axis)" };
const tick = (ms: number) => new Date(ms).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });

export function SensorTimeline({ h, episodes, journey }: { h: History; episodes: Episode[]; journey: JourneySeg[] }) {
  const valid = useMemo(() => h.readings.filter((r) => !r.flag && r.temperature_c !== null), [h]);
  const data = useMemo(() => valid.map((r) => ({
    t: new Date(r.ts).getTime(),
    temp: r.temperature_c,
    hum: r.humidity_pct,
    door: r.door_open ? r.temperature_c : null,
    shock: r.motion === "shock" ? r.temperature_c : null,
    oob: r.out_of_band,
  })), [valid]);
  const domain: [number, number] = [data[0]?.t ?? 0, data[data.length - 1]?.t ?? 1];

  // Replay: stream the journey into the chart and raise the excursion alert when it happens.
  const [idx, setIdx] = useState<number | null>(null);
  const [alert, setAlert] = useState<string | null>(null);
  const timer = useRef<number | null>(null);
  const firstOob = data.findIndex((d) => d.oob);
  const shown = idx === null ? data : data.slice(0, idx + 1);
  const stop = () => { if (timer.current) window.clearInterval(timer.current); timer.current = null; };
  const play = () => {
    stop();
    setAlert(null);
    let i = idx === null || idx >= data.length - 1 ? 0 : idx;
    const step = Math.max(1, Math.round(data.length / 160));
    timer.current = window.setInterval(() => {
      i = Math.min(data.length - 1, i + step);
      setIdx(i);
      if (firstOob >= 0 && i >= firstOob && i - step < firstOob) {
        const d = data[firstOob];
        setAlert(`Temperature excursion detected · ${tick(d.t)} · ${d.temp?.toFixed(1)} °C (limit ${h.band.max_c} °C)`);
      }
      if (i >= data.length - 1) stop();
    }, 45);
  };
  useEffect(() => stop, []);
  const playing = timer.current !== null;

  const temps = data.map((d) => d.temp as number);
  const lo = Math.min(...temps, h.band.min_c ?? h.band.max_c - 2) - 0.8;
  const hi = Math.max(...temps, h.official_threshold.max_c, h.band.max_c) + 0.8;
  const hb = h.humidity_band;
  const doors = valid.filter((r) => r.door_open).length;
  const shocks = valid.filter((r) => r.motion === "shock").length;

  return (
    <div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-ink2 mb-2">
        <Legend swatch={<span className="h-0.5 w-4 rounded bg-[var(--c-series-1)]" />} label="Temperature (°C)" />
        <Legend swatch={<span className="h-3 w-4 rounded-sm" style={{ background: "var(--c-band)" }} />} label={`Target band ${h.band.min_c ?? "—"}–${h.band.max_c} °C (demo)`} />
        <Legend swatch={<span className="h-0 w-4 border-t-2 border-dashed border-critical" />} label={`Official: ${h.official_threshold.label}`} />
        <Legend swatch={<span className="h-3 w-4 rounded-sm" style={{ background: "var(--c-exc)" }} />} label="Excursion" />
        <Legend swatch={<DoorOpen size={12} />} label={`${doors} door events`} />
        <Legend swatch={<Zap size={12} />} label={`${shocks} shocks`} />
        <div className="ml-auto flex gap-1.5">
          <button className="btn-ghost !py-1 !px-2 text-[12px]" onClick={() => (playing ? stop() : play())}>
            {playing ? <Pause size={13} /> : <Play size={13} />} {playing ? "Pause" : "Replay sensor stream"}
          </button>
          {idx !== null && (
            <button className="btn-ghost !py-1 !px-2 text-[12px]" onClick={() => { stop(); setIdx(null); setAlert(null); }}>
              <RotateCcw size={13} />
            </button>
          )}
        </div>
      </div>
      {alert && (
        <div className="mb-2 flex items-center gap-2 rounded-lg bg-critical/10 text-critical px-3 py-2 text-[13px] font-medium fade-up">
          <ThermometerSun size={15} /> {alert}
        </div>
      )}
      <div className="h-[260px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={shown} margin={{ top: 6, right: 12, bottom: 0, left: -8 }}>
            <CartesianGrid stroke="var(--c-grid)" vertical={false} />
            <XAxis dataKey="t" type="number" domain={domain} scale="time" tickFormatter={tick} tick={AXIS}
              tickLine={false} axisLine={{ stroke: "var(--c-grid)" }} minTickGap={40} />
            <YAxis domain={[Math.floor(lo), Math.ceil(hi)]} tick={AXIS} tickLine={false} axisLine={false} width={44}
              tickFormatter={(v) => `${v}°`} allowDataOverflow />
            <ReferenceArea y1={h.band.min_c ?? Math.floor(lo)} y2={h.band.max_c} fill="var(--c-band)" fillOpacity={1} ifOverflow="hidden" />
            {episodes.map((e, i) => (
              <ReferenceArea key={i} x1={new Date(e.start).getTime()} x2={new Date(e.end).getTime()}
                fill="var(--c-exc)" fillOpacity={1} ifOverflow="hidden" />
            ))}
            <ReferenceLine y={h.official_threshold.max_c} stroke="rgb(var(--critical))" strokeDasharray="5 4" ifOverflow="extendDomain" />
            {h.official_threshold.min_c !== null && (
              <ReferenceLine y={h.official_threshold.min_c} stroke="rgb(var(--critical))" strokeDasharray="5 4" />
            )}
            <Line dataKey="temp" stroke="var(--c-series-1)" strokeWidth={2} dot={false} isAnimationActive={false} connectNulls={false} />
            <Scatter dataKey="door" fill="rgb(var(--ink2))" shape="triangle" isAnimationActive={false} legendType="none" />
            <Scatter dataKey="shock" fill="rgb(var(--serious))" shape="diamond" isAnimationActive={false} legendType="none" />
            <Tooltip content={<TempTip band={h.band} />} cursor={{ stroke: "var(--c-axis)", strokeDasharray: "3 3" }} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-3 text-[12px] font-medium text-ink2">Relative humidity (%)</div>
      <div className="h-[110px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={shown} margin={{ top: 4, right: 12, bottom: 0, left: -8 }}>
            <CartesianGrid stroke="var(--c-grid)" vertical={false} />
            <XAxis dataKey="t" type="number" domain={domain} scale="time" tickFormatter={tick} tick={AXIS}
              tickLine={false} axisLine={{ stroke: "var(--c-grid)" }} minTickGap={40} />
            <YAxis domain={[(dmin: number) => Math.max(0, Math.floor(dmin - 5)), (dmax: number) => Math.min(100, Math.ceil(dmax + 5))]}
              tick={AXIS} tickLine={false} axisLine={false} width={44} tickFormatter={(v) => `${v}%`} />
            {hb.min !== null && hb.max !== null && (
              <ReferenceArea y1={hb.min} y2={hb.max} fill="var(--c-band)" fillOpacity={1} ifOverflow="hidden" />
            )}
            <Area dataKey="hum" stroke="var(--c-series-3)" strokeWidth={2} fill="var(--c-series-3)" fillOpacity={0.08}
              isAnimationActive={false} dot={false} />
            <Tooltip formatter={(v) => [`${Number(v).toFixed(1)}%`, "Humidity"]} labelFormatter={(l) => tick(Number(l))}
              contentStyle={{ background: "rgb(var(--raised))", border: "1px solid rgb(var(--line))", borderRadius: 8, fontSize: 12 }} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <JourneyStrip journey={journey} domain={domain} episodes={episodes} />
    </div>
  );
}

function Legend({ swatch, label }: { swatch: React.ReactNode; label: string }) {
  return <span className="flex items-center gap-1.5">{swatch}{label}</span>;
}

function TempTip({ active, payload, band }: any) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  const out = p.temp > band.max_c || (band.min_c !== null && p.temp < band.min_c);
  return (
    <div className="rounded-lg border border-line bg-raised px-3 py-2 text-[12px] shadow-sm">
      <div className="text-muted">{tick(p.t)}</div>
      <div className="font-semibold text-ink tabnum">{p.temp?.toFixed(2)} °C {out && <span className="text-critical">· outside band</span>}</div>
      {p.hum !== null && <div className="text-ink2 tabnum">RH {p.hum?.toFixed(1)}%</div>}
      {p.door !== null && <div className="text-ink2">Door opened</div>}
      {p.shock !== null && <div className="text-serious">Shock / mishandling</div>}
    </div>
  );
}

const SEG_STYLE: Record<string, string> = {
  transit: "bg-accent/15 text-accent",
  handling: "bg-serious/15 text-serious",
  dwell: "bg-ink2/10 text-ink2",
  distribution: "bg-good/15 text-good",
};

function JourneyStrip({ journey, domain, episodes }: { journey: JourneySeg[]; domain: [number, number]; episodes: Episode[] }) {
  const span = domain[1] - domain[0] || 1;
  return (
    <div className="mt-3">
      <div className="relative flex h-7 w-full overflow-hidden rounded-md gap-[2px] text-[10px] font-medium">
        {journey.map((s) => {
          const a = Math.max(domain[0], new Date(s.start_ts).getTime());
          const b = Math.min(domain[1], s.end_ts ? new Date(s.end_ts).getTime() : domain[1]);
          const w = Math.max(0, (100 * (b - a)) / span);
          return (
            <div key={s.seq} className={clsx("flex items-center px-1.5 truncate", SEG_STYLE[s.segment_type])}
              style={{ width: `${w}%` }} title={`${s.label} · ${s.hours ?? "?"} h`}>
              {w > 7 && <span className="truncate">{s.label}</span>}
            </div>
          );
        })}
        {episodes.map((e, i) => (
          <div key={i} className="absolute top-0 h-full bg-critical/70" title={`Excursion ${e.duration_h} h`}
            style={{ left: `${(100 * (new Date(e.start).getTime() - domain[0])) / span}%`,
              width: `${Math.max(0.4, (100 * (new Date(e.end).getTime() - new Date(e.start).getTime())) / span)}%` }} />
        ))}
      </div>
      <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-muted">
        <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-sm bg-accent/40" />Transit</span>
        <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-sm bg-serious/40" />Port / handling</span>
        <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-sm bg-ink2/25" />Cold-storage dwell</span>
        <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-sm bg-good/40" />Distribution</span>
        <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-sm bg-critical/70" />Excursion</span>
        <span className="ml-auto">{fmt.dt(new Date(domain[0]).toISOString())} → {fmt.dt(new Date(domain[1]).toISOString())}</span>
      </div>
    </div>
  );
}
