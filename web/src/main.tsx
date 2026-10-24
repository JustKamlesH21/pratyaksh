import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, NavLink, Navigate, Route, Routes } from "react-router-dom";
import "./index.css";
import BankAppPage from "./pages/BankAppPage";
import CallerPage from "./pages/CallerPage";
import ConsolePage from "./pages/ConsolePage";
import EvalPage from "./pages/EvalPage";

const tabs = [
  { to: "/console", label: "Console" },
  { to: "/call", label: "Caller" },
  { to: "/bank", label: "Bank App" },
  { to: "/eval", label: "Eval" },
];

function Shell() {
  return (
    <div className="min-h-screen">
      <header className="bg-ink text-white">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3">
          <div className="flex items-baseline gap-2">
            <span className="text-xl font-bold tracking-tight">Pratyaksh</span>
            <span className="hidden text-sm text-white/60 sm:inline">live-human verification for bank calls</span>
          </div>
          <nav className="ml-auto flex gap-1">
            {tabs.map((t) => (
              <NavLink
                key={t.to}
                to={t.to}
                className={({ isActive }) =>
                  `whitespace-nowrap rounded-md px-2 py-1.5 text-sm font-medium sm:px-3 ${isActive ? "bg-amber text-ink" : "text-white/80 hover:bg-white/10"}`
                }
              >
                {t.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">
        <Routes>
          <Route path="/" element={<Navigate to="/console" replace />} />
          <Route path="/console" element={<ConsolePage />} />
          <Route path="/call" element={<CallerPage />} />
          <Route path="/bank" element={<BankAppPage />} />
          <Route path="/eval" element={<EvalPage />} />
        </Routes>
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
