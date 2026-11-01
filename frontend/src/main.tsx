import { StrictMode, Suspense, lazy, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import {
  ChartBar, DeviceMobile, IconContext, List, Monitor, Moon, Phone, Robot, SealCheck, ShieldCheck, SquaresFour, Sun, X,
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
const DeepfakePage = lazy(() => import("./pages/DeepfakePage"));
const ConsentPage = lazy(() => import("./pages/ConsentPage"));

const tabs = [
  { to: "/demo", label: "Demo", icon: SquaresFour },
  { to: "/consent", label: "Consent", icon: SealCheck },
  { to: "/deepfake", label: "Deepfake", icon: Robot },
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

/** Under 640px the seven tabs do not fit beside the wordmark (they pushed every page to 450px wide), so a
 *  phone gets a menu with the same tabs, named. */
function PhoneMenu() {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  const Glyph = open ? X : List;
  return (
    <div className="ml-auto sm:hidden">
      <button
        className="press grid size-11 place-items-center rounded-full text-ink ring-1 ring-line"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls="phone-menu"
        aria-label={open ? "Close menu" : "Open menu"}
      >
        <Glyph size={20} weight="bold" aria-hidden />
      </button>
      {open && (
        <nav id="phone-menu" aria-label="Pages" className="motion-enter elev-2 absolute inset-x-0 top-full border-b border-line bg-surface p-3">
          <ul className="grid grid-cols-2 gap-1">
            {tabs.map(({ to, label, icon: Icon }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  className={({ isActive }) =>
                    `press flex min-h-12 items-center gap-2.5 rounded-xl px-3 text-sm font-medium ${
                      isActive ? "bg-accent/15 text-ink" : "text-ink-soft"
                    }`
                  }
                >
                  <Icon size={20} aria-hidden />
                  {label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      )}
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
  const stage = ["/demo", "/console", "/consent"].includes(location.pathname) ? stageOf(location.search) : null;
  // The Caller app and the Bank App are phone screens: they own the whole viewport (safe areas included),
  // with no site header, which on an iPhone in Safari pushed Hang up under the toolbar (Oct 30).
  const phone = ["/call", "/bank"].includes(location.pathname);
  useEffect(() => {
    if (stage) document.documentElement.dataset.stage = stage;
    else delete document.documentElement.dataset.stage;
  }, [stage]);
  return (
    <div className="min-h-[100dvh]">
      <header
        hidden={!!stage || phone}
        className={`sticky top-0 z-30 border-b backdrop-blur-md ${
          landing ? "border-transparent bg-canvas/70" : "border-line bg-surface/85"
        }`}
      >
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-3 px-4">
          <Link to="/" className="press flex items-center gap-2.5 rounded-full" aria-label="Pratyaksh home">
            <Logo />
            <span className="font-display text-base font-semibold tracking-tight sm:text-lg">Pratyaksh</span>
          </Link>
          {/* A segmented track: the current page is an accent-tinted pill with a filled icon. */}
          <PhoneMenu />
          <nav className="ml-auto hidden gap-0.5 rounded-full bg-sunken p-1 ring-1 ring-line sm:flex">
            {tabs.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                aria-label={label}
                title={label}
                className={({ isActive }) =>
                  `press flex min-h-8 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 text-sm font-medium md:px-3 ${
                    isActive ? "bg-accent/15 text-ink" : "text-ink-soft hover:text-ink"
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    <Icon size={17} weight={isActive ? "fill" : "duotone"} className={isActive ? "text-accent" : ""} aria-hidden />
                    <span className="hidden lg:inline">{label}</span>
                  </>
                )}
              </NavLink>
            ))}
          </nav>
          <button
            className="press grid size-11 shrink-0 place-items-center rounded-full text-ink-soft ring-1 ring-line hover:text-ink sm:size-10"
            onClick={cycleTheme}
            aria-label={`Colour theme: ${theme}. Change`}
            title={`Theme: ${theme}`}
          >
            <ThemeIcon size={18} aria-hidden />
          </button>
        </div>
      </header>
      <main className={landing || phone ? "" : stage ? "px-4 py-4" : "mx-auto max-w-7xl px-4 py-6"}>
        <Suspense fallback={<PageSkeleton />}>
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/demo" element={<DemoPage />} />
            <Route path="/consent" element={<ConsentPage />} />
            <Route path="/deepfake" element={<DeepfakePage />} />
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
