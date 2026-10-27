import { StrictMode, Suspense, lazy, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import {
  ChartBar, DeviceMobile, IconContext, Monitor, Moon, Phone, ShieldCheck, SquaresFour, Sun,
} from "@phosphor-icons/react";
import { Logo, stageOf } from "./components";
import "./index.css";

// One chunk per page: the Bank App on a phone does not download the LiveKit client the Caller page needs.
const LandingPage = lazy(() => import("./pages/LandingPage"));
const ConsolePage = lazy(() => import("./pages/ConsolePage"));
const CallerPage = lazy(() => import("./pages/CallerPage"));
const BankAppPage = lazy(() => import("./pages/BankAppPage"));
const EvalPage = lazy(() => import("./pages/EvalPage"));
const DemoPage = lazy(() => import("./pages/DemoPage"));

const tabs = [
  { to: "/demo", label: "Demo", icon: SquaresFour },
  { to: "/console", label: "Console", icon: ShieldCheck },
  { to: "/call", label: "Caller", icon: Phone },
  { to: "/bank", label: "Bank App", icon: DeviceMobile },
  { to: "/eval", label: "Eval", icon: ChartBar },
];

type Theme = "dark" | "light" | "system";
const NEXT: Record<Theme, Theme> = { dark: "light", light: "system", system: "dark" };
const THEME_ICON = { dark: Moon, light: Sun, system: Monitor };

function applyTheme(t: Theme) {
  if (t === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = t;
}

/** Dark by default (index.html applies it before the first paint); light, or follow the system. A change
 *  in one tab reaches the others (the projector window follows the laptop's toggle). */
function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => {
    const t = document.documentElement.dataset.theme;
    return t === "light" || t === "dark" ? t : "system";
  });
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key !== "theme") return;
      const t: Theme = e.newValue === "light" || e.newValue === "dark" ? e.newValue : e.newValue === "system" ? "system" : "dark";
      applyTheme(t);
      setTheme(t);
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);
  const cycle = () => {
    const next = NEXT[theme];
    applyTheme(next);
    try {
      localStorage.setItem("theme", next);
    } catch {
      /* storage blocked: the choice lasts for this page only */
    }
    setTheme(next);
  };
  return [theme, cycle];
}

function PageSkeleton() {
  return (
    <div className="mx-auto grid max-w-7xl gap-6 px-4 py-6 lg:grid-cols-[20rem_1fr]" aria-busy="true" aria-label="Loading">
      <div className="skeleton h-72" />
      <div className="flex flex-col gap-4">
        <div className="skeleton h-28" />
        <div className="skeleton h-52" />
      </div>
    </div>
  );
}

function Shell() {
  const [theme, cycleTheme] = useTheme();
  const ThemeIcon = THEME_ICON[theme];
  const location = useLocation();
  const landing = location.pathname === "/";
  // Stage mode (/demo?stage=1, /console?stage=1): the projector shows only the page, at 125% (112.5% with
  // stage=small). The nav goes; the theme still follows the laptop's toggle through storage.
  const stage = ["/demo", "/console"].includes(location.pathname) ? stageOf(location.search) : null;
  useEffect(() => {
    if (stage) document.documentElement.dataset.stage = stage;
    else delete document.documentElement.dataset.stage;
  }, [stage]);
  return (
    <div className="min-h-[100dvh]">
      <header
        hidden={!!stage}
        className={`sticky top-0 z-30 border-b backdrop-blur-md ${
          landing ? "border-transparent bg-canvas/70" : "border-line bg-surface/85"
        }`}
      >
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-4">
          <Link to="/" className="press flex items-center gap-2 rounded-lg" aria-label="Pratyaksh home">
            <Logo />
            <span className="font-display text-base font-semibold tracking-tight sm:text-lg">Pratyaksh</span>
          </Link>
          <nav className="ml-auto flex gap-0.5 sm:gap-1">
            {tabs.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                aria-label={label}
                className={({ isActive }) =>
                  `press flex items-center gap-1.5 whitespace-nowrap rounded-lg px-2.5 py-1.5 text-sm font-medium ${
                    isActive ? "bg-accent/12 text-accent" : "text-ink-soft hover:bg-sunken hover:text-ink"
                  }`
                }
              >
                <Icon size={17} aria-hidden />
                <span className="hidden md:inline">{label}</span>
              </NavLink>
            ))}
          </nav>
          <button
            className="press grid size-9 place-items-center rounded-lg text-ink-soft ring-1 ring-line hover:text-ink"
            onClick={cycleTheme}
            aria-label={`Colour theme: ${theme}. Change`}
            title={`Theme: ${theme}`}
          >
            <ThemeIcon size={18} aria-hidden />
          </button>
        </div>
      </header>
      <main className={landing ? "" : stage ? "px-4 py-4" : "mx-auto max-w-7xl px-4 py-6"}>
        <Suspense fallback={<PageSkeleton />}>
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/demo" element={<DemoPage />} />
            <Route path="/console" element={<ConsolePage />} />
            <Route path="/call" element={<CallerPage />} />
            <Route path="/bank" element={<BankAppPage />} />
            <Route path="/eval" element={<EvalPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <IconContext.Provider value={{ weight: "duotone", size: 18 }}>
      <BrowserRouter>
        <Shell />
      </BrowserRouter>
    </IconContext.Provider>
  </StrictMode>,
);
