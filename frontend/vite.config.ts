import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { type Plugin, type ServerOptions, defineConfig } from "vite";

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

/** HTTPS on the demo LAN (start.ps1 sets PRATYAKSH_HTTPS=1 when .env has HTTPS=1): phones allow the
 *  microphone only on HTTPS. One origin serves everything, so a phone trusts one certificate:
 *  /v1 goes to the verifier, /rtc to LiveKit's signalling (media still flows over UDP). */
function lanHttps(): ServerOptions {
  if (process.env.PRATYAKSH_HTTPS !== "1") return {};
  const keys = resolve(fileURLToPath(new URL(".", import.meta.url)), "..", "data", "keys");
  return {
    host: true,
    https: { key: readFileSync(resolve(keys, "lan-https.key")), cert: readFileSync(resolve(keys, "lan-https.crt")) },
    proxy: {
      "/v1": { target: "http://127.0.0.1:8000", ws: true },
      "/rtc": { target: "ws://127.0.0.1:7880", ws: true },
    },
  };
}

/** iOS offers to install the CA as a profile only when it arrives as application/x-x509-ca-cert. */
function caDownload(): Plugin {
  return {
    name: "pratyaksh-ca-download",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use("/pratyaksh-ca.crt", (_req, res) => {
        const file = resolve(fileURLToPath(new URL(".", import.meta.url)), "public", "pratyaksh-ca.crt");
        res.setHeader("Content-Type", "application/x-x509-ca-cert");
        res.end(readFileSync(file));
      });
    },
  };
}

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    preloadFonts(["geist-latin-wght-normal", "bricolage-grotesque-latin-opsz-normal"]),
    caDownload(),
  ],
  server: { port: 5173, ...lanHttps() },
});
