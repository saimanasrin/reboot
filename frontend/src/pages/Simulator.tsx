import { ArrowRight, LoaderCircle, Radio } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useUser } from "../App";
import { api } from "../api";
import { Card, ClassBadge, SimNotice } from "../components/ui";

const PRODUCTS = [
  ["P-STRAW", "Fresh strawberries", 500], ["P-FISH", "Fresh fish", 200], ["P-CHICK", "Fresh chicken", 800],
  ["P-MILK", "Fresh milk", 1200], ["P-YOG", "Yogurt", 600], ["P-LEAFY", "Leafy vegetables", 300],
  ["P-FROZMEAT", "Frozen meat", 3000], ["P-TOM", "Fresh tomatoes", 1000],
] as const;

export default function Simulator() {
  const user = useUser();
  const allowed = user?.role === "admin" || user?.role === "warehouse_manager";
  const [scenarios, setScenarios] = useState<Record<string, { label: string; description: string }>>({});
  const [customers, setCustomers] = useState<{ customer_id: string; name: string; discount_channel: boolean }[]>([]);
  const [product, setProduct] = useState<string>("P-STRAW");
  const [scenario, setScenario] = useState("B_excursion");
  const [qty, setQty] = useState(500);
  const [customer, setCustomer] = useState("C-DC");
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<any[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api("/simulator/scenarios").then(setScenarios).catch(() => {});
    api("/customers").then(setCustomers).catch(() => {});
  }, []);

  async function run() {
    setBusy(true); setErr(null);
    try {
      const r = await api("/simulator/shipments", { body: { product_id: product, scenario, quantity_kg: qty, original_customer_id: customer } });
      setResults((x) => [{ ...r, product, scenario }, ...x]);
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  return (
    <div className="p-4 md:p-6 space-y-4 max-w-[1200px] mx-auto">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2"><Radio size={20} className="text-accent" /> IoT sensor simulator</h1>
        <p className="text-sm text-ink2 mt-1 max-w-3xl">
          Generate a synthetic reefer journey (temperature, humidity, GPS, door, motion/shock, battery) and push it through
          the full pipeline: data-quality screen → feature reconstruction → shelf-life prediction → compliance → routing.
        </p>
      </div>
      <SimNotice text="Prototype sensor simulation based on sensor variables and operating ranges documented by Qatar cold-chain/IoT providers and MOPH guidance." />

      <Card title="New simulated shipment">
        <div className="grid md:grid-cols-4 gap-3">
          <label className="text-[12px] text-ink2 space-y-1">Product
            <select className="input w-full" value={product} onChange={(e) => {
              setProduct(e.target.value); setQty(PRODUCTS.find((p) => p[0] === e.target.value)![2]);
            }}>
              {PRODUCTS.map(([id, n]) => <option key={id} value={id}>{n}</option>)}
            </select>
          </label>
          <label className="text-[12px] text-ink2 space-y-1">Quantity (kg)
            <input className="input w-full" type="number" min={1} max={50000} value={qty} onChange={(e) => setQty(Number(e.target.value))} />
          </label>
          <label className="text-[12px] text-ink2 space-y-1 md:col-span-2">Original customer
            <select className="input w-full" value={customer} onChange={(e) => setCustomer(e.target.value)}>
              {customers.filter((c) => !c.discount_channel).map((c) => <option key={c.customer_id} value={c.customer_id}>{c.name}</option>)}
            </select>
          </label>
        </div>
        <div className="mt-4 grid sm:grid-cols-2 lg:grid-cols-5 gap-2">
          {Object.entries(scenarios).map(([k, v]) => (
            <button key={k} onClick={() => setScenario(k)}
              className={`text-left rounded-lg border p-3 transition ${scenario === k ? "border-accent bg-accent/[0.07]" : "border-line hover:bg-page"}`}>
              <div className="text-sm font-semibold">{v.label}</div>
              <div className="text-[12px] text-muted leading-snug">{v.description}</div>
            </button>
          ))}
        </div>
        <div className="mt-4 flex items-center gap-3">
          <button className="btn-primary" disabled={busy || !allowed} onClick={run}>
            {busy ? <LoaderCircle size={15} className="animate-spin" /> : <Radio size={15} />} Simulate & analyse
          </button>
          {!allowed && <span className="text-[12px] text-muted">Requires Admin or Warehouse Manager role.</span>}
          {err && <span className="text-sm text-critical">{err}</span>}
        </div>
      </Card>

      {results.length > 0 && (
        <Card title="Simulated shipments (this session)" bodyClass="!px-0">
          <ul className="divide-y divide-line">
            {results.map((r) => (
              <li key={r.shipment_id} className="flex flex-wrap items-center gap-3 px-4 py-2.5">
                <span className="font-semibold">{r.shipment_id}</span>
                <span className="text-sm text-ink2">{PRODUCTS.find((p) => p[0] === r.product)?.[1]} · {scenarios[r.scenario]?.label}</span>
                <ClassBadge c={r.classification} withAction />
                <span className="text-sm tabnum">{r.estimated_remaining_days.toFixed(1)} d usable</span>
                <Link to={`/shipments/${r.shipment_id}`} className="ml-auto btn-ghost !py-1">Open <ArrowRight size={14} /></Link>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title="Device ingestion API">
        <p className="text-sm text-ink2 mb-2">Gateways push readings with a device key (never exposed to the browser). Each batch is validated, stored and re-analysed.</p>
        <pre className="text-[12px] bg-page rounded-lg p-3 overflow-x-auto border border-line">{`POST /api/sensors/ingest
X-Device-Key: <QCHAIN_DEVICE_API_KEY>
{
  "device_id": "VQ-IOT-4821",
  "shipment_id": "Q4821",
  "readings": [{ "ts": "2026-09-25T14:10:00", "temperature_c": 4.1, "humidity_pct": 74.0,
                 "lat": 25.195, "lon": 51.445, "door_open": false, "motion": "stationary", "battery_pct": 88.0 }]
}`}</pre>
      </Card>
    </div>
  );
}
