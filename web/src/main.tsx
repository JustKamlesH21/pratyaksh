import { StrictMode, Suspense, lazy, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, NavLink, Navigate, Route, Routes } from "react-router-dom";
import "./index.css";

// One chunk per page: the Bank App on a phone does not download the LiveKit client the Caller page needs.
const ConsolePage = lazy(() => import("./pages/ConsolePage"));
const CallerPage = lazy(() => import("./pages/CallerPage"));
const BankAppPage = lazy(() => import("./pages/BankAppPage"));
const EvalPage = lazy(() => import("./pages/EvalPage"));

const tabs = [
  { to: "/console", label: "Console" },
  { to: "/call", label: "Caller" },
  { to: "/bank", label: "Bank App" },
  { to: "/eval", label: "Eval" },
];

type Theme = "auto" | "light" | "dark";
const NEXT: Record<Theme, Theme> = { auto: "light", light: "dark", dark: "auto" };

function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => {
    const t = document.documentElement.dataset.theme;
    return t === "light" || t === "dark" ? t : "auto";
  });
  const cycle = () => {
    const next = NEXT[theme];
    if (next === "auto") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = next;
    try {
      if (next === "auto") localStorage.removeItem("theme");
      else localStorage.setItem("theme", next);
    } catch {
      /* storage blocked: the choice lasts for this page only */
    }
    setTheme(next);
  };
  return [theme, cycle];
}

function PageSkeleton() {
  return (
    <div className="grid gap-6 lg:grid-cols-[20rem_1fr]" aria-busy="true" aria-label="Loading">
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
  return (
    <div className="min-h-[100dvh]">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-4">
          <div className="flex items-baseline gap-2">
            <span className="text-lg font-semibold tracking-tight">Pratyaksh</span>
            <span className="hidden text-sm text-ink-soft md:inline">live-human verification for bank calls</span>
          </div>
          <nav className="ml-auto flex gap-1">
            {tabs.map((t) => (
              <NavLink
                key={t.to}
                to={t.to}
                className={({ isActive }) =>
                  `press whitespace-nowrap rounded-lg px-2.5 py-1.5 text-sm font-medium sm:px-3 ${
                    isActive ? "bg-accent/10 text-accent" : "text-ink-soft hover:bg-sunken hover:text-ink"
                  }`
                }
              >
                {t.label}
              </NavLink>
            ))}
          </nav>
          <button
            className="press hidden rounded-lg px-2.5 py-1.5 text-sm font-medium text-ink-soft ring-1 ring-line hover:text-ink sm:block"
            onClick={cycleTheme}
            aria-label={`Colour theme: ${theme}. Change`}
            title="Colour theme"
          >
            {theme === "auto" ? "Auto" : theme === "light" ? "Light" : "Dark"}
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">
        <Suspense fallback={<PageSkeleton />}>
          <Routes>
            <Route path="/" element={<Navigate to="/console" replace />} />
            <Route path="/console" element={<ConsolePage />} />
            <Route path="/call" element={<CallerPage />} />
            <Route path="/bank" element={<BankAppPage />} />
            <Route path="/eval" element={<EvalPage />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  </StrictMode>,
);
