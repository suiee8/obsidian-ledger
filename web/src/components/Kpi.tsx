import { useCountUp } from "../lib/useCountUp";

type Tone = "profit" | "loss" | "neutral";

interface KpiProps {
  label: string;
  value: number | null;
  format: (value: number) => string;
  tone?: Tone;
  note?: string;
}

const TONE_CLASS: Record<Tone, string> = {
  profit: "kpi-value tone-profit",
  loss: "kpi-value tone-loss",
  neutral: "kpi-value",
};

/** One headline number. Numbers count up unless the user prefers reduced motion. */
export function Kpi({ label, value, format, tone = "neutral", note }: KpiProps) {
  const animated = useCountUp(value ?? 0);
  const shown = value === null ? "—" : format(value === null ? 0 : animated);
  return (
    <article className="glass kpi">
      <p className="label">{label}</p>
      <p className={TONE_CLASS[tone]} aria-label={`${label}: ${value === null ? "not available" : format(value)}`}>
        {shown}
      </p>
      {note && <p className="kpi-note">{note}</p>}
    </article>
  );
}
