import clsx from "clsx";
import { BookOpen, Boxes, FlaskConical, LayoutDashboard, LogOut, Moon, Radio, Sun } from "lucide-react";
import { createContext, useContext, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { session, type User } from "./api";
import About from "./pages/About";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import ShipmentDetail from "./pages/ShipmentDetail";
import Shipments from "./pages/Shipments";
import Simulator from "./pages/Simulator";

const UserCtx = createContext<User | null>(null);
export const useUser = () => useContext(UserCtx);

const ThemeCtx = createContext<boolean>(false);
export const useDark = () => useContext(ThemeCtx);

const ROLE_LABEL: Record<string, string> = {
  admin: "Admin", warehouse_manager: "Warehouse Manager", distributor: "Distributor", retailer: "Retailer",
};

function useTheme(): [boolean, () => void] {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try { localStorage.setItem("qchain-theme", dark ? "dark" : "light"); } catch { /* ignore */ }
  }, [dark]);
  return [dark, () => setDark((d) => !d)];
}

export default function App() {
  const [user, setUser] = useState<User | null>(session.user());
  const [dark, toggle] = useTheme();
  const nav = useNavigate();

  useEffect(() => {
    session.onUnauthorized(() => { setUser(null); nav("/login"); });
  }, [nav]);

  if (!user) {
    return (
      <ThemeCtx.Provider value={dark}>
        <Routes>
          <Route path="*" element={<Login onLogin={setUser} dark={dark} toggleTheme={toggle} />} />
        </Routes>
      </ThemeCtx.Provider>
    );
  }

  const links = [
    { to: "/", label: "Command centre", icon: <LayoutDashboard size={17} />, end: true },
    { to: "/shipments", label: "Shipments", icon: <Boxes size={17} /> },
    { to: "/simulator", label: "Sensor simulator", icon: <Radio size={17} /> },
    { to: "/about", label: "Method & sources", icon: <BookOpen size={17} /> },
  ];

  return (
    <UserCtx.Provider value={user}>
      <ThemeCtx.Provider value={dark}>
        <div className="flex h-full">
          <aside className="hidden md:flex w-60 shrink-0 flex-col border-r border-line bg-surface">
            <div className="px-5 pt-5 pb-6">
              <div className="flex items-center gap-2.5">
                <div className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-white font-bold">Q</div>
                <div>
                  <div className="font-semibold leading-tight">Q-Chain AI</div>
                  <div className="text-[11px] text-muted leading-tight">Cold-chain decision layer</div>
                </div>
              </div>
            </div>
            <nav className="flex-1 px-3 space-y-0.5">
              {links.map((l) => (
                <NavLink key={l.to} to={l.to} end={l.end}
                  className={({ isActive }) => clsx("flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium",
                    isActive ? "bg-accent/10 text-accent" : "text-ink2 hover:bg-page hover:text-ink")}>
                  {l.icon}{l.label}
                </NavLink>
              ))}
            </nav>
            <div className="m-3 rounded-lg border border-dashed border-line p-3 text-[11px] text-muted leading-relaxed">
              <div className="flex items-center gap-1.5 font-semibold text-ink2 mb-1"><FlaskConical size={12} /> Prototype</div>
              Synthetic sensor data. Estimates remaining usable <em>quality</em> — never food safety, never the legal expiry.
            </div>
          </aside>

          <div className="flex-1 min-w-0 flex flex-col">
            <header className="h-14 shrink-0 border-b border-line bg-surface flex items-center gap-3 px-4 md:px-6">
              <div className="md:hidden font-semibold">Q-Chain AI</div>
              <nav className="md:hidden flex gap-1 overflow-x-auto">
                {links.map((l) => (
                  <NavLink key={l.to} to={l.to} end={l.end} className={({ isActive }) =>
                    clsx("p-2 rounded-lg", isActive ? "text-accent bg-accent/10" : "text-ink2")}>{l.icon}</NavLink>
                ))}
              </nav>
              <div className="hidden lg:flex items-center gap-2 text-[12px] text-muted">
                <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full rounded-full bg-good opacity-60 animate-ping" /><span className="relative inline-flex h-2 w-2 rounded-full bg-good" /></span>
                Live simulation clock · 25 Sep 2026, 14:00 AST
              </div>
              <div className="ml-auto flex items-center gap-2">
                <button className="btn-ghost !p-2" onClick={toggle} aria-label="Toggle theme">
                  {dark ? <Sun size={16} /> : <Moon size={16} />}
                </button>
                <div className="hidden sm:block text-right leading-tight">
                  <div className="text-sm font-medium">{user.name}</div>
                  <div className="text-[11px] text-muted">{ROLE_LABEL[user.role]}</div>
                </div>
                <button className="btn-ghost !p-2" aria-label="Sign out"
                  onClick={() => { session.clear(); setUser(null); nav("/"); }}>
                  <LogOut size={16} />
                </button>
              </div>
            </header>
            <main className="flex-1 overflow-y-auto">
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/shipments" element={<Shipments />} />
                <Route path="/shipments/:id" element={<ShipmentDetail />} />
                <Route path="/simulator" element={<Simulator />} />
                <Route path="/about" element={<About />} />
                <Route path="*" element={<Navigate to="/" />} />
              </Routes>
            </main>
          </div>
        </div>
      </ThemeCtx.Provider>
    </UserCtx.Provider>
  );
}
