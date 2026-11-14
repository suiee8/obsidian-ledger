# Visual refresh (Phase 6C)

## Roles

- Charcoal is the reading canvas: tables, forms, long text, panels.
- Royal blue is brand and structure: rail, hero band, primary actions, selection, chart emphasis.
- White is emphasis and light: headline numbers, shader highlights, focus rings, key icons.
- Profit and loss colors stay on P&L only. No other hue.

## Worst-case contrast

Panels are charcoal at 92% opacity, so at most 8% of the background shows through. The worst
background behind a panel is royal 500, which gives a panel color of about `#151B2A`.

| Text | Background | Ratio |
| --- | --- | --- |
| White | Royal 500 (lightest blue text sits on) | 4.85:1 |
| White | Royal 600 | 6.61:1 |
| White | Royal 700 | 9.19:1 |
| White | Panel, worst case | 17.18:1 |
| Ink | Panel, worst case | 14.51:1 |
| Muted | Panel, worst case | 6.85:1 |
| Royal 300 | Panel, worst case | 7.83:1 |

Text on blue is always `--on-blue` (white). The light ink token on royal 500 is below 4.5:1, so it
is not used there (covered by `src/shader/white.test.ts`). The hero's light royal 500 glow sits at
the right edge, away from the heading.

## Shader and Pause background

The shader keeps its royal flow and adds thin white highlights. The white added is capped at 15%
of the final luminance (`WHITE_CAP`, the same formula in `fragment.glsl`). The Pause background
button (top bar, and the command palette) stops the animation and shows a static frame. The choice
is saved on this machine only, and it starts paused when the OS asks for reduced motion.

## Tests

- `e2e/aa-visual-refresh.spec.ts` measures color balance on 1440x900 screenshots, covers the
  toggle and the fallback, and writes the screenshots and video to `docs/screens`.
- The balance numbers are saved in `docs/screens/color-balance.json`.
- The Dashboard and Import targets leave a window of about one percentage point, because
  almost every pixel is blue or charcoal. Changing hero heights or the fallback wash intensity
  moves these numbers; re-run the spec after any such change.
