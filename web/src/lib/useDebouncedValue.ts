import { useEffect, useState } from "react";

/** Returns `value` once it has stayed unchanged for `delayMs`. Used so typing in a filter does not
 *  start a request for every keystroke. */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [settled, setSettled] = useState(value);

  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);

  return settled;
}
