import type { z } from "zod";

import type { DashboardSchema } from "./schemas";

export type DashboardData = z.infer<typeof DashboardSchema>;
