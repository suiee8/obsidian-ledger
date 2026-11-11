// Renders the PWA icons from web/icons/icon.svg into web/public.
// Run with: pnpm -C web icons
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { Resvg } from "@resvg/resvg-js";

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(resolve(here, "../icons/icon.svg"));
const outputs = [
  { file: "icon-192.png", size: 192 },
  { file: "icon-512.png", size: 512 },
  { file: "apple-touch-icon.png", size: 180 },
];

for (const { file, size } of outputs) {
  const png = new Resvg(source, { fitTo: { mode: "width", value: size } }).render().asPng();
  writeFileSync(resolve(here, "../public", file), png);
  console.log(`wrote public/${file} (${size}x${size}, ${png.length} bytes)`);
}
