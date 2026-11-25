import { create } from "zustand";

import type { Commit, Preview } from "./schemas";

export interface ImportedFile {
  file: File;
  preview: Preview;
  result: Commit;
  options: Record<string, unknown>;
}

export const useImportSession = create<{ files: ImportedFile[] }>(() => ({ files: [] }));
