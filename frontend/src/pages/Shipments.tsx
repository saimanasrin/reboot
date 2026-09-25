import clsx from "clsx";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, CLASS_META, fmt, type Classification } from "../api";
import { Card, ClassBadge, ErrorBox, RiskBadge, Spinner } from "../components/ui";
import { LifeBar } from "./Dashboard";

const PRODUCTS = [
  ["", "All products"], ["P-STRAW", "Strawberries"], ["P-FISH", "Fresh fish"], ["P-CHICK", "Fresh chicken"],
  ["P-MILK", "Fresh milk"], ["P-YOG", "Yogurt"], ["P-LEAFY", "Leafy vegetables"], ["P-FROZMEAT", "Frozen meat"],
  ["P-TOM", "Tomatoes"],
];
const PAGE = 25;

export default function Shipments() {
  const [cls, setCls] = useState<Classification | "">("");
  const [product, setProduct] = useState("");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("priority");
  const [page, setPage] = useState(0);
  const [data, setData] = useState<{ total: number; items: any[] } | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const nav = useNavigate();

  useEffect(() => {
    const p = new URLSearchParams({ limit: String(PAGE), offset: String(page * PAGE), sort });
    if (cls) p.set("classification", cls);
    if (product) p.set("product_id", product);
    if (q) p.set("q", q);
    const t = setTimeout(() => api(`/shipments?${p}`).then(setData).catch(setErr), q ? 250 : 0);
    return () => clearTimeout(t);
  }, [cls, product, q, sort, page]);

  return (
    <div className="p-4 md:p-6 space-y-4 max-w-[1600px] mx-auto">
      <h1 className="text-2xl font-semibold tracking-tight">Shipments</h1>
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search size={15} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
          <input className="input pl-8 w-64" placeholder="Search ID, product, location" value={q}
            onChange={(e) => { setQ(e.target.value); setPage(0); }} />
        </div>
        <select className="input" value={product} onChange={(e) => { setProduct(e.target.value); setPage(0); }}>
          {PRODUCTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <select className="input" value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="priority">Sort: urgency</option>
          <option value="remaining">Sort: usable life</option>
          <option value="quantity">Sort: quantity</option>
          <option value="id">Sort: ID</option>
        </select>
        <div className="flex gap-1">
          {(["", "GOOD", "MID", "LOW", "HOLD"] as const).map((c) => (
            <button key={c} onClick={() => { setCls(c); setPage(0); }}
              className={clsx("rounded-full border px-3 py-1 text-[12px] font-medium",
                cls === c ? "border-accent bg-accent/10 text-accent" : "border-line text-ink2 hover:bg-surface")}>
              {c ? `${CLASS_META[c].label} · ${CLASS_META[c].action}` : "All"}
            </button>
          ))}
        </div>
      </div>
      {err ? <ErrorBox error={err} /> : !data ? <Spinner /> : (
        <Card bodyClass="!px-0 !pt-0 overflow-x-auto">
          <table className="w-full">
            <thead className="border-b border-line">
              <tr>
                <th className="th pl-4">Shipment</th><th className="th">Product</th><th className="th text-right">Quantity</th>
                <th className="th">Remaining usable life</th><th className="th">Status</th><th className="th">Risk</th>
                <th className="th text-right">Confidence</th><th className="th text-right">Data quality</th>
                <th className="th">Location</th><th className="th">Recommended action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.items.map((r) => (
                <tr key={r.shipment_id} className="cursor-pointer hover:bg-page" onClick={() => nav(`/shipments/${r.shipment_id}`)}>
                  <td className="td pl-4 font-semibold">{r.shipment_id}</td>
                  <td className="td">{r.product}</td>
                  <td className="td text-right tabnum">{fmt.kg(r.quantity_kg)}</td>
                  <td className="td"><LifeBar est={r.estimated_remaining_days} declared={r.declared_remaining_days} /></td>
                  <td className="td"><ClassBadge c={r.classification} /></td>
                  <td className="td"><RiskBadge r={r.risk_level} /></td>
                  <td className="td text-right tabnum">{fmt.pct(r.confidence * 100)}</td>
                  <td className="td text-right tabnum">{fmt.pct(r.data_quality)}</td>
                  <td className="td text-ink2">{r.location}</td>
                  <td className="td font-medium">{r.recommended_action}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex items-center justify-between px-4 pt-3 text-sm text-muted">
            <span className="tabnum">{data.total === 0 ? "No shipments" : `${page * PAGE + 1}–${Math.min(data.total, (page + 1) * PAGE)} of ${data.total}`}</span>
            <div className="flex gap-1">
              <button className="btn-ghost !p-1.5" disabled={page === 0} onClick={() => setPage(page - 1)} aria-label="Previous page"><ChevronLeft size={16} /></button>
              <button className="btn-ghost !p-1.5" disabled={(page + 1) * PAGE >= data.total} onClick={() => setPage(page + 1)} aria-label="Next page"><ChevronRight size={16} /></button>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
