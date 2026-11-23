# Glyph field baseline

Step 0 stopped because two background layers respond to the pointer. The foreground cursor trail is listed separately because the request also calls it out as a possible source of ambiguity.

| Layer | Drawing, region, and stacking | Pointer mapping and disable controls | Color source |
| --- | --- | --- | --- |
| [WaveGridBackground](https://github.com/suiee8/obsidian-ledger/blob/450e8d49dd7fe8a3871bb3bd426cb4026065e530/web/src/components/WaveGridBackground.tsx#L146) | A lit WebGL cube grid with cursor and idle ripples. Shell lazy-loads it in main. Its fixed canvas is clipped to the rounded main region at z-index 0, behind foreground content. [Layer CSS](../web/src/components/shell-effects.css#L483) | The main pointer listener normalizes viewport coordinates and raycasts to the cube tops. Touch events are ignored. Reduced motion hides the canvas, and `data-shader="off"` disables it. The render scheduler skips hidden tabs and handles context loss. [Pointer handler](https://github.com/suiee8/obsidian-ledger/blob/450e8d49dd7fe8a3871bb3bd426cb4026065e530/web/src/components/WaveGridBackground.tsx#L363) | The shader mixes lit cube shading with white crests using `vec3(1.0)`. White is a shader constant, and there is no glyph-ready CSS color token read by this layer. |
| [SapphireAurora](../web/src/shader/SapphireAurora.tsx#L199) | A WebGL aurora and line detail with ambient motion and an additional pointer shift. Shell lazy-loads its fixed canvas in the rounded main ambient wrapper at z-index −1, beneath the hero and wave grid. [Pointer shift](../web/src/shader/fragment.glsl#L39) | A window pointer listener normalizes viewport coordinates and updates the eased shader uniform. `data-shader="off"` or unavailable WebGL uses the fallback. The controller pauses in hidden tabs and can step down to a static frame. The component initializes reduced motion and save-data as false, and the pointer listener does not filter touch. [Listener and controller setup](../web/src/shader/SapphireAurora.tsx#L207) | Reads multiple CSS tokens, including `--palette-background`, the royal blues, `--palette-ice`, and `--palette-white`. A root attribute observer refreshes the colors. [Token reader](../web/src/shader/SapphireAurora.tsx#L41) |
| [CursorEffects](../web/src/components/CursorEffects.tsx#L13) | A short cursor-following scribble on a fixed viewport canvas at z-index 9997, above the page and beneath the custom cursor and pulse. The canvas is portaled into the body. [Layer CSS](../web/src/components/shell-effects.css#L70) | Uses viewport coordinates directly. It requires a fine pointer and accepts mouse input only. Reduced motion disables it, and blur or native-control hover clears cursor feedback. [Pointer handler](../web/src/components/CursorEffects.tsx#L147) | Reads the `--white-24` CSS token when mounted. |

The current app has no “Pause effects” control. The initial baseline stopped here. The follow-up authorized continuing. WaveGridBackground was selected because it draws the cursor-reactive cube grid.

## Baseline checks

`pnpm check` passed with 59 web tests and 409 API tests passing, 1 API test skipped, and zero lint or type-check errors. No dev server was running. No e2e specs were run.

## Replacement

`GlyphFieldBackground` replaces the cube renderer inside the existing lazy shell layer. The rounded clip, 50% layer opacity, hit testing, and stacking stay in the shell stylesheet. The separate SapphireAurora and foreground CursorEffects are untouched. The glyphs use `--palette-white` for the old shader's white and `--font-mono` for the self-hosted JetBrains Mono font. Three.js and its types had no remaining callers.

The canvas is sized and mapped to the visible intersection of main and the viewport. The offscreen atlas has 24 alpha levels. The ambient cache updates at about 12 fps and redraws changed cells. The hover pass composites that cache, then clears and redraws nearby cells. Idle ambient refreshes also update the matching visible cells directly, avoiding full-canvas copies. Reduced motion freezes the ambient phase and updates hover on input. Touch-only devices disable the effect. The existing app exposes no “Pause effects” button, so the renderer accepts the root state `data-effects="paused"` without adding a control.

Compared with the direct HTML reference, the cached ambient phase advances at a lower cadence than the cursor-local phase. The renderer quantizes opacity, omits hover contributions below 0.01, and feathers the glyph positions using refresh-rate-independent easing. The existing layer opacity is applied by CSS after the canvas draw. The reduced-motion fidelity test compares premultiplied RGBA with the direct renderer and enforces a mean absolute difference below 2/255.

## Performance and bundles

Chromium with SwiftShader, 1440 × 900 at DPR 1. Both builds used the same scripted pointer path over main for approximately five seconds. SapphireAurora used its fallback in both runs to isolate the layer under test. These cloud-software results do not establish performance on the i5-1235U. The baseline returned only five frame intervals, so its percentiles are especially noisy.

| Metric | Wave grid | Glyph field |
| --- | ---: | ---: |
| Frame interval p50 | 1,183.3 ms | 150.0 ms |
| Frame interval p95 | 2,049.9 ms | 766.6 ms |
| Whole-page scripting per sampled frame, mean | 88.15 ms | 8.80 ms |
| Effect animation callback scripting, p95 | 3.66 ms | 2.08 ms |
| Effect animation callback scripting, max | 3.74 ms | 14.07 ms |
| Idle renderer main-thread task share, three-second trace window | 2.63% | 9.74% |
| Idle Chromium process CPU, separate three-second sample (100% = one core) | 193.85% | 202.94% |
| Lazy background chunk, gzipped | 135.02 kB | 2.96 kB |
| Initial JS, gzipped | 134.24 kB | 134.24 kB |

The cloud trace improved frame intervals and scripting, with higher idle CPU and occasional hover callbacks over the 2 ms budget. The strict per-frame budget remains unverified on the target laptop.

## Final verification

The focused production-preview Playwright run passed nine Dashboard, navigation, and effects tests. Dashboard axe passed at 1440 px and 390 px. The glyph tests passed the pixel-difference threshold, checked pointer brightening and the pause state, and confirmed touch-only devices hide the canvas. There were no new CSP violations. Both production builds emit the existing blocked Zod JIT probe from the entry bundle, which the targeted glyph check excludes. The full e2e suite was not run.

Final `pnpm check` passed with 64 web tests and 409 API tests passing, one API test skipped, and zero lint or type-check errors.
