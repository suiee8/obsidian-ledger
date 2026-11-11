// Deletes the local data folder the API writes: the DuckDB database, the raw Parquet copies, and
// rejected-row exports. Nothing outside that folder is touched. Stop the API first, because the
// database file stays locked while the API has it open.
//
//   pnpm reset:data                 deletes api/.ledger-data
//   pnpm reset:data -- <folder>     deletes that folder instead (also read from LEDGER_DATA_DIR)

import { existsSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2).filter((arg) => arg !== "--");
const requested = args[0] ?? process.env.LEDGER_DATA_DIR;
const target = requested ? resolve(requested) : join(root, "api", ".ledger-data");

// Refuse anything that is not clearly a data folder, so a typo cannot delete a project.
if (target === root || target === dirname(root) || dirname(target) === target) {
  console.error(`Refusing to delete ${target}: it is not a data folder.`);
  process.exit(1);
}

if (!existsSync(target)) {
  console.log(`Nothing to reset: ${target} does not exist.`);
} else {
  rmSync(target, { recursive: true, force: true });
  console.log(`Removed ${target}`);
}
