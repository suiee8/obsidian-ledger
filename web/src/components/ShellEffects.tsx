import type { CSSProperties } from "react";

export function LiquidFilter() {
  return (
    <svg className="shell-liquid-filter" width="0" height="0" aria-hidden="true">
      <filter id="ledger-liquid-edge">
        <feTurbulence type="fractalNoise" baseFrequency="0.035 0.08" numOctaves="2" seed="4" />
        <feDisplacementMap in="SourceGraphic" scale="5" xChannelSelector="R" yChannelSelector="G" />
      </filter>
    </svg>
  );
}

export function FlipBrand() {
  const name = "Obsidian Ledger";
  return (
    <>
      <span className="sr-only">{name}</span>
      <span className="shell-flip-brand" aria-hidden="true">
        {Array.from(name, (letter, index) => letter === " " ? " " : (
          <span
            key={index}
            data-char={letter}
            style={{ "--flip-delay": `${Math.sin((index / name.length) * Math.PI / 2) * 0.55}s` } as CSSProperties}
          >
            {letter}
          </span>
        ))}
      </span>
    </>
  );
}

const SOCIALS = [
  { label: "GitHub", letter: "G", href: "https://github.com/suiee8" },
  { label: "LinkedIn", letter: "L", href: "https://www.linkedin.com/in/madhvikpanchal" },
  { label: "Email", letter: "M", href: "mailto:themadhvik@gmail.com" },
] as const;

function SocialIcon({ label }: { label: (typeof SOCIALS)[number]["label"] }) {
  if (label === "LinkedIn") return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
      <path d="M3 8h4v13H3zm2-6a2 2 0 1 1 0 4 2 2 0 0 1 0-4zm5 6h4v1.7a4 4 0 0 1 7 2.7V21h-4v-7.4c0-2.6-3-2.5-3 0V21h-4z" />
    </svg>
  );
  if (label === "Email") return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="m3 7 9 6 9-6" />
    </svg>
  );
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 .9a11.1 11.1 0 0 0-3.5 21.64c.55.1.76-.24.76-.53v-2.07c-3.09.67-3.74-1.3-3.74-1.3-.51-1.28-1.24-1.62-1.24-1.62-1.01-.69.08-.68.08-.68 1.12.08 1.71 1.15 1.71 1.15 1 1.7 2.62 1.21 3.26.92.1-.72.39-1.21.7-1.49-2.47-.28-5.06-1.23-5.06-5.49 0-1.21.43-2.2 1.15-2.98-.12-.29-.5-1.42.11-2.96 0 0 .94-.3 3.05 1.14a10.6 10.6 0 0 1 5.55 0c2.12-1.44 3.05-1.14 3.05-1.14.61 1.54.23 2.67.11 2.96.71.78 1.15 1.77 1.15 2.98 0 4.27-2.6 5.2-5.08 5.48.4.35.75 1.02.75 2.06v3.04c0 .29.2.64.77.53A11.1 11.1 0 0 0 12 .9Z" />
    </svg>
  );
}

export function SocialFooter() {
  return (
    <footer className="shell-social-footer">
      <nav className="shell-social-links" aria-label="Social links">
        {SOCIALS.map(({ label, letter, href }, index) => (
          <a
            key={label}
            className="shell-social-link"
            href={href}
            aria-label={label}
            target={label === "Email" ? undefined : "_blank"}
            rel={label === "Email" ? undefined : "noopener noreferrer"}
            style={{ "--social-delay": `${index * 80}ms` } as CSSProperties}
          >
            <span className="shell-social-tooltip" aria-hidden="true">{label}</span>
            <span className="shell-social-card" aria-hidden="true">
              <span className="shell-social-front">{letter}</span>
              <span className="shell-social-back"><SocialIcon label={label} /></span>
            </span>
          </a>
        ))}
      </nav>
    </footer>
  );
}
