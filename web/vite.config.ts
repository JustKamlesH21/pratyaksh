import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { type Plugin, defineConfig } from "vite";

/** Preload the Latin UI and display fonts, so the first paint is already in the right typeface
 *  (no swap from a fallback). Other scripts load only when a page uses them (unicode-range). */
function preloadFonts(names: string[]): Plugin {
  let base = "/";
  return {
    name: "preload-fonts",
    apply: "build",
    configResolved(config) {
      base = config.base;
    },
    transformIndexHtml: {
      order: "post",
      handler(_html, ctx) {
        return Object.keys(ctx.bundle ?? {})
          .filter((file) => file.endsWith(".woff2") && names.some((n) => file.includes(`/${n}-`)))
          .map((file) => ({
            tag: "link",
            attrs: { rel: "preload", as: "font", type: "font/woff2", href: `${base}${file}`, crossorigin: "" },
            injectTo: "head" as const,
          }));
      },
    },
  };
}

export default defineConfig({
  plugins: [react(), tailwindcss(), preloadFonts(["geist-latin-wght-normal", "bricolage-grotesque-latin-opsz-normal"])],
  server: { port: 5173 },
});
