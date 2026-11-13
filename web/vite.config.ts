import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vitest/config";
import { VitePWA } from "vite-plugin-pwa";

// Vite's dev server injects an inline React Refresh preamble, so only the dev server may allow inline scripts.
const contentSecurityPolicy = (scriptSrc: string) =>
  `default-src 'self'; script-src ${scriptSrc}; connect-src 'self' http://127.0.0.1:8000 http://localhost:8000 ws://127.0.0.1:5173 ws://localhost:5173; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'`;

const securityHeaders = (scriptSrc: string) => ({
  "Content-Security-Policy": contentSecurityPolicy(scriptSrc),
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  "X-Frame-Options": "DENY",
  "Permissions-Policy":
    "accelerometer=(), camera=(), geolocation=(), gyroscope=(), microphone=(), payment=(), usb=()",
});

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg", "apple-touch-icon.png", "icon-192.png", "icon-512.png"],
      manifest: {
        name: "Obsidian Ledger",
        short_name: "Ledger",
        description: "Local-first trading journal. Not financial advice.",
        theme_color: "#0B0D11",
        background_color: "#0B0D11",
        display: "standalone",
        start_url: "/",
        icons: [
          { src: "icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "icon-512.png", sizes: "512x512", type: "image/png" },
        ],
      },
    }),
  ],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    headers: securityHeaders("'self' 'unsafe-inline'"),
  },
  preview: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    headers: securityHeaders("'self'"),
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
