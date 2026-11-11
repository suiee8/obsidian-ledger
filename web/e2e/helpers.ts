import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import type { APIRequestContext } from "@playwright/test";

export const API = "http://127.0.0.1:8000";

/** The 1,000-trade sample. Playwright runs from web/, so the samples folder is one level up. */
export const SAMPLE_PATH = resolve(process.cwd(), "..", "samples", "synthetic_preview.csv");

/** Import the sample through the API, the same preview and commit steps the Import screen uses.
 *  Importing the same file again adds nothing, so tests can call this freely. */
export async function importSample(request: APIRequestContext): Promise<void> {
  const preview = await request.post(
    `${API}/api/imports/preview?filename=synthetic_preview.csv`,
    { data: readFileSync(SAMPLE_PATH), headers: { "content-type": "text/csv" } },
  );
  if (!preview.ok()) throw new Error(`preview failed: ${preview.status()} ${await preview.text()}`);
  const { preview_id: previewId } = (await preview.json()) as { preview_id: string };
  const commit = await request.post(`${API}/api/imports/${previewId}/commit`, { data: {} });
  if (!commit.ok()) throw new Error(`commit failed: ${commit.status()} ${await commit.text()}`);
}
