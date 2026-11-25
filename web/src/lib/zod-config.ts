import { z } from "zod";

// Configure validation before application modules construct their schemas.
z.config({ jitless: true });
