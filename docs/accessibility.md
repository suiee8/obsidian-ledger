# Accessibility notes

## Navigation and motion

- Use **Skip to content** to bypass the top bar and navigation. The rail exposes the current page, and the social links have accessible names.
- The decorative arrow, trail, and click pulse are hidden from assistive technology. The overlay sits above the shell and Coach, and text fields, selects, disabled controls, and resize handles keep native cursors.
- The shell respects reduced motion for the custom cursor, liquid click effect, wordmark, and social links. The wordmark remains readable and the links remain keyboard accessible.

## Sapphire Aurora contrast boundary

The shader canvas is decorative, marked `aria-hidden`, and excluded from pointer interaction. Interactive content remains in the foreground. Glass panels use a 92%-opaque
`surface-1` charcoal background (`#11141A`); browsers without backdrop-filter support receive the same
fully opaque charcoal fallback. The CSS `@supports` fallback removes translucency when neither the
standard nor prefixed backdrop-filter property is available.

The brightest shader token is ice (`#C9D6FF`). Compositing the panel at 92% opacity over that token
produces approximately `#20242C`; primary text (`#E8ECF4`) has a 13.14:1 contrast ratio. As a more
conservative bound, treating the underlying pixel as pure white produces approximately `#24272C`
under the panel and a 12.65:1 primary-text contrast ratio. The CSS-only fallback uses only the same
token palette and is behind these panels.

Screenshot and axe E2E runs set `data-shader="off"` before page initialization so the decorative
background does not affect visual determinism. The shell regression checks cover pointer visibility over Coach, native form cursors, reduced motion, and contact links. The axe suite checks the desktop and mobile layouts. Separate shader tests cover the decorative canvas, fallback rendering, and tab visibility.

- [Shell effects tests](../web/e2e/shell-effects.spec.ts)
- [axe checks](../web/e2e/a11y.spec.ts)
