type IllustrationKind = "empty" | "error" | "unavailable";

/** Simple line drawings for empty, error and not-available states. Decorative only. */
export function Illustration({ kind }: { kind: IllustrationKind }) {
  return (
    <svg className="illustration" viewBox="0 0 96 72" width="96" height="72" aria-hidden="true" focusable="false">
      {kind === "empty" && (
        <>
          <rect className="ill-line" x="14" y="10" width="68" height="52" rx="8" />
          <path className="ill-accent" d="M26 48 38 36l10 8 12-16 10 10" />
          <path className="ill-line" d="M26 22h22" />
        </>
      )}
      {kind === "error" && (
        <>
          <path className="ill-line" d="M48 10 82 62H14Z" strokeLinejoin="round" />
          <path className="ill-accent" d="M48 28v16" />
          <path className="ill-accent" d="M48 52v.5" />
        </>
      )}
      {kind === "unavailable" && (
        <>
          <circle className="ill-line" cx="48" cy="36" r="24" strokeDasharray="4 5" />
          <path className="ill-accent" d="M31 53 65 19" />
          <path className="ill-line" d="M38 36h20" />
        </>
      )}
    </svg>
  );
}
