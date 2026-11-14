import { useUi } from "../state/ui";
import { Illustration } from "./Illustration";

/** Shown when the current filters select no trades, or nothing has been imported yet. */
export function EmptyScreen({ title, body }: { title: string; body: string }) {
  const setRoute = useUi((state) => state.setRoute);
  return (
    <section className="glass empty-state" aria-labelledby="empty-screen-title">
      <Illustration kind="empty" />
      <div>
        <p className="eyebrow">Nothing to show yet</p>
        <h1 id="empty-screen-title" className="screen-title">
          {title}
        </h1>
        <p className="lede">{body}</p>
      </div>
      <button type="button" className="btn btn-primary" onClick={() => setRoute("import")}>
        Import a file
      </button>
    </section>
  );
}

export function ScreenError({
  title,
  message,
  onRetry,
}: {
  title: string;
  message: string;
  onRetry: () => void;
}) {
  return (
    <section className="glass panel" role="alert">
      <Illustration kind="error" />
      <h2 className="panel-title">{title}</h2>
      <p className="muted">{message}</p>
      <button type="button" className="btn" onClick={onRetry}>
        Try again
      </button>
    </section>
  );
}

export function ScreenSkeleton({ label }: { label: string }) {
  return (
    <div className="dashboard" aria-busy="true" aria-label={label}>
      <div className="bento">
        <div className="glass panel span-12 skeleton skeleton-tall" />
      </div>
    </div>
  );
}

/** The sentence under every analysis screen. */
export const DISCLAIMER =
  "Past performance review only. Obsidian Ledger does not give financial advice or trade signals.";
