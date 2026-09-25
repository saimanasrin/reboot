import L from "leaflet";
import { useMemo } from "react";
import { CircleMarker, MapContainer, Marker, Polyline, Popup, TileLayer, Tooltip } from "react-leaflet";
import { useNavigate } from "react-router-dom";
import { useDark } from "../App";
import type { Classification } from "../api";

export const CLASS_HEX: Record<"light" | "dark", Record<Classification, string>> = {
  light: { GOOD: "#0ca30c", MID: "#d69600", LOW: "#e26e40", HOLD: "#801620" },
  dark: { GOOD: "#0ca30c", MID: "#fab219", LOW: "#ec835a", HOLD: "#c43c48" },
};

export interface MapPoint {
  shipment_id: string; product: string; lat: number; lon: number; classification: Classification;
  estimated_remaining_days: number; quantity_kg: number; location: string; featured?: boolean; risk_level?: string;
}

function tiles(dark: boolean) {
  return dark
    ? "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    : "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
}

const QATAR_CENTER: [number, number] = [25.28, 51.35];

export default function FleetMap({ points, visible, height = 440, route, focus }: {
  points: MapPoint[];
  visible?: Set<Classification>;
  height?: number;
  route?: { lat: number; lon: number; label?: string }[];
  focus?: { lat: number; lon: number; zoom?: number };
}) {
  const dark = useDark();
  const nav = useNavigate();
  const pal = CLASS_HEX[dark ? "dark" : "light"];
  const shown = useMemo(
    () => points.filter((p) => !visible || visible.has(p.classification))
      // draw calm points first so at-risk ones sit on top
      .sort((a, b) => order(b.classification) - order(a.classification) || Number(!!a.featured) - Number(!!b.featured)),
    [points, visible],
  );
  const featured = points.filter((p) => p.featured);
  const pulse = (color: string) => L.divIcon({
    className: "",
    iconSize: [36, 36],
    iconAnchor: [18, 18],
    html: `<div style="position:relative;width:36px;height:36px">
      <span class="pulse-ring" style="position:absolute;inset:6px;border-radius:9999px;background:${color}"></span>
      <span style="position:absolute;inset:11px;border-radius:9999px;background:${color};border:2px solid white"></span></div>`,
  });

  return (
    <div style={{ height }} className="rounded-lg overflow-hidden border border-line">
      <MapContainer center={focus ? [focus.lat, focus.lon] : QATAR_CENTER} zoom={focus?.zoom ?? 9}
        scrollWheelZoom={false} style={{ height: "100%", width: "100%" }} preferCanvas>
        <TileLayer key={dark ? "d" : "l"} url={tiles(dark)}
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' />
        {route && route.length > 1 && (
          <Polyline positions={route.map((r) => [r.lat, r.lon] as [number, number])}
            pathOptions={{ color: dark ? "#3987e5" : "#2a78d6", weight: 2, dashArray: "6 6" }} />
        )}
        {shown.map((p) => (
          <CircleMarker key={p.shipment_id} center={[p.lat, p.lon]} radius={p.classification === "GOOD" ? 3.5 : 5.5}
            pathOptions={{ color: dark ? "#1a1a19" : "#ffffff", weight: 1, fillColor: pal[p.classification], fillOpacity: 0.9 }}
            eventHandlers={{ click: () => nav(`/shipments/${p.shipment_id}`) }}>
            <Tooltip direction="top" offset={[0, -4]}>
              <strong>{p.shipment_id}</strong> · {p.product}<br />
              {p.classification} · {p.estimated_remaining_days.toFixed(1)} d usable · {Math.round(p.quantity_kg)} kg<br />
              {p.location}
            </Tooltip>
          </CircleMarker>
        ))}
        {featured.filter((p) => !visible || visible.has(p.classification)).map((p) => (
          <Marker key={`f-${p.shipment_id}`} position={[p.lat, p.lon]} icon={pulse(pal[p.classification])}
            eventHandlers={{ click: () => nav(`/shipments/${p.shipment_id}`) }}>
            <Popup>
              <strong>{p.shipment_id}</strong> · {p.product}<br />
              {p.estimated_remaining_days.toFixed(1)} d usable · {p.classification}
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}

function order(c: Classification) {
  return { GOOD: 3, MID: 2, LOW: 1, HOLD: 0 }[c];
}
