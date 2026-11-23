import { useEffect, useRef } from "react";

import {
  ALPHA_LEVELS,
  COLOR_TOKEN,
  CONFIG,
  FONT_TOKEN,
  INFLUENCE_THRESHOLD,
  computeEaseFactor,
  computeFalloff,
  computeGlyphIndex,
} from "./glyphField";

export default function WaveGridBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const region = canvas.parentElement?.closest("main") ?? canvas.parentElement;
    if (!region) return;

    const hostCanvas: HTMLCanvasElement = canvas;
    const hostRegion: HTMLElement = region;

    let disposed = false;
    let dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    let width = 0;
    let height = 0;
    let cols = 0;
    let rows = 0;
    let cachedRect = hostRegion.getBoundingClientRect();
    let scrollRaf = 0;

    let currentColor = "";
    let currentFont = "";
    let spriteW = 0;
    let spriteH = 0;
    let atlasCanvas: HTMLCanvasElement | null = null;
    let ambientCanvas: HTMLCanvasElement | null = null;

    let ambientFps = 12;
    let currentRadius = CONFIG.radius;
    let staticModeOnly = false;
    let ambientTimer = 0;
    let hoverRaf = 0;
    let lastFrameTime = 0;

    // Performance window tracking
    const frameTimes: number[] = [];
    let perfWindowStart = performance.now();

    const mouse = {
      x: -9999,
      y: -9999,
      sx: -9999,
      sy: -9999,
      active: false,
    };

    let isIntersecting = true;
    let isFocused = document.hasFocus ? document.hasFocus() : true;
    const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");

    const isShaderOff = () => document.documentElement.dataset.shader === "off";
    const isPaused = () =>
      document.hidden || !isFocused || !isIntersecting || isShaderOff();

    function readStyleTokens() {
      const style = getComputedStyle(document.documentElement);
      const color = style.getPropertyValue(COLOR_TOKEN).trim();
      const font =
        style.getPropertyValue(FONT_TOKEN).trim() ||
        "JetBrains Mono, ui-monospace, monospace";
      return { color, font };
    }

    async function ensureFontLoaded(fontFamily: string) {
      if (typeof document !== "undefined" && document.fonts?.load) {
        try {
          await document.fonts.load(`400 ${CONFIG.fontSize * dpr}px ${fontFamily}`);
        } catch {
          // Fall back gracefully if loading fails
        }
      }
    }

    function buildSpriteAtlas(color: string, font: string) {
      currentColor = color;
      currentFont = font;
      spriteW = Math.ceil(CONFIG.cell * dpr);
      spriteH = Math.ceil(CONFIG.cell * dpr);

      atlasCanvas = document.createElement("canvas");
      atlasCanvas.width = CONFIG.glyphs.length * spriteW;
      atlasCanvas.height = ALPHA_LEVELS * spriteH;

      const actx = atlasCanvas.getContext("2d");
      if (!actx) return;

      actx.font = `400 ${CONFIG.fontSize * dpr}px ${font}`;
      actx.textAlign = "center";
      actx.textBaseline = "middle";

      for (let l = 0; l < ALPHA_LEVELS; l++) {
        const k = l / (ALPHA_LEVELS - 1);
        const alpha = CONFIG.baseAlpha + CONFIG.hoverAlpha * k;
        const sy = l * spriteH;

        for (let g = 0; g < CONFIG.glyphs.length; g++) {
          const sx = g * spriteW;
          actx.save();
          actx.globalAlpha = alpha;
          actx.fillStyle = color;
          actx.fillText(
            CONFIG.glyphs[g]!,
            sx + spriteW / 2,
            sy + spriteH / 2,
          );
          actx.restore();
        }
      }
    }

    function initAmbientCanvas() {
      if (!width || !height) return;
      if (!ambientCanvas) {
        ambientCanvas = document.createElement("canvas");
      }
      ambientCanvas.width = Math.ceil(width * dpr);
      ambientCanvas.height = Math.ceil(height * dpr);
    }

    function refreshAmbient(timeMs: number) {
      if (!ambientCanvas || !atlasCanvas || !cols || !rows) return;
      const actx = ambientCanvas.getContext("2d");
      if (!actx) return;

      actx.clearRect(0, 0, ambientCanvas.width, ambientCanvas.height);
      const t = timeMs * 0.001 * CONFIG.speed;
      const glyphCount = CONFIG.glyphs.length;

      for (let j = 0; j < rows; j++) {
        const py = Math.round(j * CONFIG.cell * dpr);
        const destY = py - Math.floor(spriteH / 2);

        for (let i = 0; i < cols; i++) {
          const idx = computeGlyphIndex(i, j, t, 0, glyphCount);
          const px = Math.round(i * CONFIG.cell * dpr);
          const destX = px - Math.floor(spriteW / 2);
          const sx = idx * spriteW;
          const sy = 0; // Level 0 corresponds to baseAlpha

          actx.drawImage(
            atlasCanvas,
            sx,
            sy,
            spriteW,
            spriteH,
            destX,
            destY,
            spriteW,
            spriteH,
          );
        }
      }

      // If hover loop is not active, copy ambient directly to the main canvas
      if (!hoverRaf) {
        const ctx = hostCanvas.getContext("2d");
        if (ctx) {
          ctx.clearRect(0, 0, hostCanvas.width, hostCanvas.height);
          ctx.drawImage(ambientCanvas, 0, 0);
        }
      }
    }

    function scheduleAmbient() {
      if (ambientTimer) {
        clearTimeout(ambientTimer);
        ambientTimer = 0;
      }
      if (disposed || isPaused() || reducedMotion.matches || staticModeOnly || ambientFps <= 0) {
        return;
      }
      ambientTimer = window.setTimeout(() => {
        if (!disposed && !isPaused()) {
          refreshAmbient(performance.now());
          scheduleAmbient();
        }
      }, 1000 / ambientFps);
    }

    function drawHoverFrame(t: number) {
      if (!ambientCanvas || !atlasCanvas) return;
      const ctx = hostCanvas.getContext("2d");
      if (!ctx) return;

      // Composite the ambient layer as base
      ctx.clearRect(0, 0, hostCanvas.width, hostCanvas.height);
      ctx.drawImage(ambientCanvas, 0, 0);

      if (!mouse.active && Math.abs(mouse.x - mouse.sx) < 0.05 && Math.abs(mouse.y - mouse.sy) < 0.05) {
        return;
      }

      const glyphCount = CONFIG.glyphs.length;
      const radius = currentRadius;
      const maxDist = radius * 1.5;
      const minI = Math.max(0, Math.floor((mouse.sx - maxDist) / CONFIG.cell));
      const maxI = Math.min(cols - 1, Math.ceil((mouse.sx + maxDist) / CONFIG.cell));
      const minJ = Math.max(0, Math.floor((mouse.sy - maxDist) / CONFIG.cell));
      const maxJ = Math.min(rows - 1, Math.ceil((mouse.sy + maxDist) / CONFIG.cell));

      type ActiveCell = {
        i: number;
        j: number;
        k: number;
        dx: number;
        dy: number;
      };
      const activeCells: ActiveCell[] = [];

      for (let j = minJ; j <= maxJ; j++) {
        for (let i = minI; i <= maxI; i++) {
          const baseX = i * CONFIG.cell;
          const baseY = j * CONFIG.cell;
          const dx = baseX - mouse.sx;
          const dy = baseY - mouse.sy;
          const d2 = dx * dx + dy * dy;
          const k = computeFalloff(d2, radius);
          if (k > INFLUENCE_THRESHOLD) {
            activeCells.push({ i, j, k, dx, dy });
          }
        }
      }

      // Pass 1: Clear all influenced cells so nudged glyph overlaps stay exact
      for (let c = 0; c < activeCells.length; c++) {
        const item = activeCells[c]!;
        const basePx = Math.round(item.i * CONFIG.cell * dpr);
        const basePy = Math.round(item.j * CONFIG.cell * dpr);
        const destX = basePx - Math.floor(spriteW / 2);
        const destY = basePy - Math.floor(spriteH / 2);
        ctx.clearRect(destX, destY, spriteW, spriteH);
      }

      // Pass 2: Draw all influenced cells at their nudged positions
      for (let c = 0; c < activeCells.length; c++) {
        const item = activeCells[c]!;
        const { i, j, k, dx, dy } = item;
        let x = i * CONFIG.cell;
        let y = j * CONFIG.cell;

        if (k > 0.001) {
          const len = Math.sqrt(dx * dx + dy * dy) || 1;
          x += (dx / len) * CONFIG.push * k;
          y += (dy / len) * CONFIG.push * k;
        }

        const idx = computeGlyphIndex(i, j, t, k, glyphCount);
        const level = Math.min(
          ALPHA_LEVELS - 1,
          Math.max(0, Math.round(k * (ALPHA_LEVELS - 1))),
        );

        const px = Math.round(x * dpr);
        const py = Math.round(y * dpr);
        const destX = px - Math.floor(spriteW / 2);
        const destY = py - Math.floor(spriteH / 2);
        const sx = idx * spriteW;
        const sy = level * spriteH;

        ctx.drawImage(
          atlasCanvas,
          sx,
          sy,
          spriteW,
          spriteH,
          destX,
          destY,
          spriteW,
          spriteH,
        );
      }
    }

    function checkAdaptiveStepDown(now: number, dt: number) {
      frameTimes.push(dt);
      if (now - perfWindowStart >= 2000) {
        if (frameTimes.length >= 20) {
          const sorted = [...frameTimes].sort((a, b) => a - b);
          const p95 = sorted[Math.floor(sorted.length * 0.95)] || 0;
          if (p95 > 20) {
            if (ambientFps > 6) {
              ambientFps = 6;
            } else if (currentRadius > 130) {
              currentRadius = 130;
            } else {
              staticModeOnly = true;
              ambientFps = 0;
              if (ambientTimer) {
                clearTimeout(ambientTimer);
                ambientTimer = 0;
              }
            }
          }
        }
        frameTimes.length = 0;
        perfWindowStart = now;
      }
    }

    function hoverLoop(now: number) {
      hoverRaf = 0;
      if (disposed || isPaused()) {
        lastFrameTime = 0;
        return;
      }

      const dt = lastFrameTime ? Math.min(now - lastFrameTime, 100) : 16.67;
      lastFrameTime = now;
      checkAdaptiveStepDown(now, dt);

      if (mouse.active) {
        const ease = computeEaseFactor(CONFIG.follow, dt);
        mouse.sx += (mouse.x - mouse.sx) * ease;
        mouse.sy += (mouse.y - mouse.sy) * ease;
      }

      const t = reducedMotion.matches ? 0 : now * 0.001 * CONFIG.speed;
      drawHoverFrame(t);

      const dx = mouse.x - mouse.sx;
      const dy = mouse.y - mouse.sy;
      const dist2 = dx * dx + dy * dy;
      const settling = mouse.active || dist2 > 0.04;

      if (settling && !reducedMotion.matches) {
        hoverRaf = requestAnimationFrame(hoverLoop);
      } else {
        lastFrameTime = 0;
      }
    }

    function startHover() {
      if (!hoverRaf && !disposed && !isPaused() && !reducedMotion.matches) {
        lastFrameTime = 0;
        hoverRaf = requestAnimationFrame(hoverLoop);
      }
    }

    function stopHover() {
      if (hoverRaf) {
        cancelAnimationFrame(hoverRaf);
        hoverRaf = 0;
      }
      lastFrameTime = 0;
      if (ambientCanvas) {
        const ctx = hostCanvas.getContext("2d");
        if (ctx) {
          ctx.clearRect(0, 0, hostCanvas.width, hostCanvas.height);
          ctx.drawImage(ambientCanvas, 0, 0);
        }
      }
    }

    function onPointerMove(e: PointerEvent) {
      if (e.pointerType === "touch" || isPaused()) return;
      mouse.x = e.clientX - cachedRect.left;
      mouse.y = e.clientY - cachedRect.top;

      if (!mouse.active) {
        mouse.sx = mouse.x;
        mouse.sy = mouse.y;
        mouse.active = true;
      }

      if (reducedMotion.matches) {
        mouse.sx = mouse.x;
        mouse.sy = mouse.y;
        drawHoverFrame(0);
      } else {
        startHover();
      }
    }

    function onPointerLeave() {
      mouse.active = false;
      mouse.x = -9999;
      mouse.y = -9999;
      mouse.sx = -9999;
      mouse.sy = -9999;
      stopHover();
    }

    function updateRect() {
      cachedRect = hostRegion.getBoundingClientRect();
    }

    function onScroll() {
      if (!scrollRaf) {
        scrollRaf = requestAnimationFrame(() => {
          scrollRaf = 0;
          updateRect();
        });
      }
    }

    async function handleResize() {
      if (disposed) return;
      dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      width = Math.max(1, hostRegion.clientWidth);
      height = Math.max(1, hostRegion.clientHeight);
      updateRect();

      hostCanvas.width = Math.ceil(width * dpr);
      hostCanvas.height = Math.ceil(height * dpr);
      cols = Math.ceil(width / CONFIG.cell) + 1;
      rows = Math.ceil(height / CONFIG.cell) + 1;

      const { color, font } = readStyleTokens();
      await ensureFontLoaded(font);
      if (disposed) return;

      buildSpriteAtlas(color, font);
      initAmbientCanvas();
      refreshAmbient(performance.now());
      if (mouse.active) {
        drawHoverFrame(performance.now() * 0.001 * CONFIG.speed);
      }
    }

    async function handleThemeChange() {
      if (disposed) return;
      const { color, font } = readStyleTokens();
      if (color !== currentColor || font !== currentFont) {
        await ensureFontLoaded(font);
        if (disposed) return;
        buildSpriteAtlas(color, font);
        refreshAmbient(performance.now());
        if (mouse.active) {
          drawHoverFrame(performance.now() * 0.001 * CONFIG.speed);
        }
      }
    }

    function onVisibilityChange() {
      if (isPaused()) {
        stopHover();
        if (ambientTimer) {
          clearTimeout(ambientTimer);
          ambientTimer = 0;
        }
      } else {
        scheduleAmbient();
        if (mouse.active) startHover();
      }
    }

    function onFocus() {
      isFocused = true;
      onVisibilityChange();
    }

    function onBlur() {
      isFocused = false;
      onVisibilityChange();
    }

    const resizeObserver = new ResizeObserver(() => {
      void handleResize();
    });
    resizeObserver.observe(hostRegion);

    const intersectionObserver = new IntersectionObserver((entries) => {
      const entry = entries[0];
      isIntersecting = entry ? entry.isIntersecting : true;
      onVisibilityChange();
    });
    intersectionObserver.observe(hostRegion);

    const mutationObserver = new MutationObserver(() => {
      if (isShaderOff()) {
        stopHover();
        if (ambientTimer) {
          clearTimeout(ambientTimer);
          ambientTimer = 0;
        }
        hostCanvas.hidden = true;
      } else {
        hostCanvas.hidden = false;
        void handleThemeChange();
        scheduleAmbient();
      }
    });
    mutationObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "data-cb", "data-theme", "data-shader", "style"],
    });

    const onMotionChange = () => {
      if (reducedMotion.matches) {
        if (ambientTimer) {
          clearTimeout(ambientTimer);
          ambientTimer = 0;
        }
        stopHover();
        refreshAmbient(0);
      } else {
        scheduleAmbient();
      }
    };
    reducedMotion.addEventListener("change", onMotionChange);

    hostRegion.addEventListener("pointermove", onPointerMove, { passive: true });
    hostRegion.addEventListener("pointerleave", onPointerLeave);
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("focus", onFocus);
    window.addEventListener("blur", onBlur);
    document.addEventListener("visibilitychange", onVisibilityChange);

    void handleResize();
    scheduleAmbient();

    return () => {
      disposed = true;
      if (ambientTimer) clearTimeout(ambientTimer);
      if (hoverRaf) cancelAnimationFrame(hoverRaf);
      if (scrollRaf) cancelAnimationFrame(scrollRaf);
      resizeObserver.disconnect();
      intersectionObserver.disconnect();
      mutationObserver.disconnect();
      reducedMotion.removeEventListener("change", onMotionChange);
      hostRegion.removeEventListener("pointermove", onPointerMove);
      hostRegion.removeEventListener("pointerleave", onPointerLeave);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("blur", onBlur);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, []);

  return (
    <div className="wave-grid-layer" aria-hidden="true">
      <canvas ref={canvasRef} aria-hidden="true" style={{ pointerEvents: "none" }} />
    </div>
  );
}
