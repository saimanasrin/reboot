import { Bot, LoaderCircle, Send, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { api } from "../api";
import { Chip } from "./ui";

interface AgentOut {
  what_happened: string; why_prediction_changed: string; recommended_action: string;
  alternatives: { option: string; assessment: string }[]; answer: string; citations: string[];
  _meta: { engine: "llm" | "template"; model: string | null; guardrails: string[] };
}

const SUGGESTIONS = [
  "Why did the shelf life drop?",
  "What happens if we do nothing?",
  "Why not send everything to Retailer B?",
  "Can any of this go to a food bank?",
];

export default function AgentPanel({ shipmentId }: { shipmentId: string }) {
  const [q, setQ] = useState("");
  const [out, setOut] = useState<AgentOut | null>(null);
  const [asked, setAsked] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function ask(question: string | null, e?: FormEvent) {
    e?.preventDefault();
    setBusy(true); setErr(null); setAsked(question);
    try { setOut(await api<AgentOut>(`/shipments/${shipmentId}/agent-explanation`, { body: { question } })); setQ(""); }
    catch (ex) { setErr(ex instanceof Error ? ex.message : String(ex)); }
    finally { setBusy(false); }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <button className="btn-ghost" disabled={busy} onClick={() => ask(null)}><Bot size={15} /> Generate briefing</button>
        {SUGGESTIONS.map((s) => (
          <button key={s} disabled={busy} onClick={() => ask(s)}
            className="rounded-full border border-line px-3 py-1 text-[12px] text-ink2 hover:bg-page">{s}</button>
        ))}
      </div>
      <form onSubmit={(e) => ask(q || null, e)} className="flex gap-2">
        <input className="input flex-1" maxLength={1000} placeholder="Ask about this shipment…" value={q} onChange={(e) => setQ(e.target.value)} />
        <button className="btn-primary" disabled={busy}>{busy ? <LoaderCircle size={15} className="animate-spin" /> : <Send size={15} />}</button>
      </form>
      {err && <div className="text-sm text-critical">{err}</div>}
      {out && (
        <div className="rounded-xl border border-line bg-raised p-4 space-y-3 fade-up">
          <div className="flex flex-wrap items-center gap-2">
            <Chip tone={out._meta.engine === "llm" ? "accent" : "neutral"} icon={<Bot size={12} />}>
              {out._meta.engine === "llm" ? `LLM narration · ${out._meta.model}` : "Deterministic template explainer"}
            </Chip>
            {asked && <span className="text-[12px] text-muted">Q: {asked}</span>}
          </div>
          {out.answer && <Sec t="Answer">{out.answer}</Sec>}
          <Sec t="What happened">{out.what_happened}</Sec>
          <Sec t="Why the prediction changed">{out.why_prediction_changed}</Sec>
          <Sec t="Recommended action">{out.recommended_action}</Sec>
          {out.alternatives.length > 0 && (
            <Sec t="Alternatives">
              <ul className="list-disc pl-5 space-y-0.5">
                {out.alternatives.map((a, i) => <li key={i}><strong className="font-medium">{a.option}:</strong> {a.assessment}</li>)}
              </ul>
            </Sec>
          )}
          <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
            Cited data: {out.citations.map((c) => <code key={c} className="rounded bg-line/60 px-1">{c}</code>)}
          </div>
          <ul className="text-[11px] text-muted space-y-0.5">
            {out._meta.guardrails.map((g, i) => <li key={i} className="flex gap-1.5"><ShieldCheck size={12} className="mt-0.5 shrink-0" />{g}</li>)}
          </ul>
        </div>
      )}
      <p className="text-[11px] text-muted">
        The assistant only narrates structured engine outputs. It cannot change predictions, classifications,
        compliance status or routing, and it never assesses food safety.
      </p>
    </div>
  );
}

function Sec({ t, children }: { t: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">{t}</div>
      <div className="text-sm text-ink leading-relaxed">{children}</div>
    </div>
  );
}
