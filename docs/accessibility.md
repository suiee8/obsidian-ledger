# Accessibility notes

## Sapphire Aurora contrast boundary

The shader is decorative and has no accessible name; its canvas is `aria-hidden` and does not receive
pointer events. Interactive content remains in the foreground. Glass panels use a 92%-opaque
`surface-1` charcoal background (`#11141A`); browsers without backdrop-filter support receive the same
solid charcoal fallback.

The brightest shader token is ice (`#C9D6FF`). Compositing the panel at 92% opacity over that token
produces approximately `#20242C`; primary text (`#E8ECF4`) has a 13.14:1 contrast ratio. As a more
conservative bound, treating the underlying pixel as pure white produces approximately `#24272C`
under the panel and a 12.65:1 primary-text contrast ratio. The CSS-only fallback uses only the same
token palette and is behind these panels.

Screenshot and axe E2E runs set `data-shader="off"` before page initialization so the decorative
background does not affect visual determinism. The shader-specific tests cover the accessible canvas
name boundary, reduced motion, fallback, and tab visibility handling.
