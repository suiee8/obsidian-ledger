import type { ReactNode } from "react";

export function ChartFallback({ sizeClass }: { sizeClass: string }) {
  return <div className={`chart skeleton ${sizeClass}`} aria-busy="true" aria-label="Loading chart" />;
}

/** A glass card with a heading. The section is named by its title for screen readers. */
export function Panel({
  title,
  className = "",
  children,
}: {
  title: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={`glass panel ${className}`} aria-label={title}>
      <h2 className="panel-title">{title}</h2>
      {children}
    </section>
  );
}