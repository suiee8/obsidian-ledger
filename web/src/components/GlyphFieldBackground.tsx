import { useEffect, useRef } from "react";

import { CONFIG, createAtlas, easing, isPaused, paintGlyphs, readGlyphStyle } from "./glyph-field";

export default function GlyphFieldBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const region = canvas?.closest("main");
    const ctx = canvas?.getContext("2d");
    const ambient = document.createElement("canvas");
    const cache = ambient.getContext("2d");
    if (!canvas || !region || !ctx || !cache) return;

    const root = document.documentElement;
    const reduced = matchMedia("(prefers-reduced-motion: reduce)");
    const fine = matchMedia("(any-pointer: fine)");
    const coarse = matchMedia("(any-pointer: coarse)");
    const contrast = matchMedia("(forced-colors: active)");
    const listeners = new AbortController();
    const { signal } = listeners;
    const disabled = () => root.dataset.shader === "off" || root.dataset.effects === "paused"
      || (coarse.matches && !fine.matches);
    let visible = false;
    const paused = () => isPaused(document.hidden, document.hasFocus(), visible, disabled());

    let atlas: ReturnType<typeof createAtlas> | undefined;
    let styleKey = "";
    let fontRequest = 0;
    let resolution: MediaQueryList | undefined;
    let dpr = 1;
    let left = 0, top = 0, width = 0, height = 0;
    let timer = 0, frame = 0, layoutFrame = 0;
    let ambientTime = 0;
    let ambientIndices: Uint8Array | undefined;
    let ambientShown = false;
    let stage = 0, sampleStart = 0, slow = 0, samples = 0;
    let last = 0, lastInput = 0;
    let pointer: { x: number; y: number } | undefined;
    let glow: typeof pointer;

    function composite() {
      ctx!.globalCompositeOperation = "copy";
      ctx!.drawImage(ambient, 0, 0, ambient.width / dpr, ambient.height / dpr);
      ctx!.globalCompositeOperation = "source-over";
      ambientShown = true;
    }

    function refreshAmbient() {
      window.clearTimeout(timer);
      if (paused() || !atlas || !width || !height) return;
      ambientTime = reduced.matches || stage >= 3 ? 0 : performance.now() * 0.001 * CONFIG.speed;
      ambientIndices ??= new Uint8Array(
        (Math.ceil(width / CONFIG.cell) + 1) * (Math.ceil(height / CONFIG.cell) + 1),
      ).fill(255);
      const mirror = !glow && !frame && ambientShown ? ctx! : undefined;
      paintGlyphs(cache!, atlas, width, height, ambientTime, undefined, ambientIndices, mirror);
      if (!frame) {
        if (glow) paintHover(performance.now(), glow);
        else if (!mirror) composite();
      }
      if (!reduced.matches && stage < 3) timer = window.setTimeout(refreshAmbient, stage ? 167 : 83);
    }

    function tick(now: number) {
      frame = 0;
      if (paused() || !pointer || !atlas || !width || !height) return;
      const dt = last ? now - last : 16.67;
      if (last && !reduced.matches && stage < 3) {
        sampleStart ||= now;
        samples++;
        if (dt > 20) slow++;
        if (now - sampleStart >= 2000) {
          if (slow / samples > 0.05 && ++stage === 3) refreshAmbient();
          sampleStart = slow = samples = 0;
        }
      }
      last = now;
      glow ??= { ...pointer };
      const alpha = reduced.matches ? 1 : easing(dt);
      glow.x += (pointer.x - glow.x) * alpha;
      glow.y += (pointer.y - glow.y) * alpha;
      paintHover(now, glow);
      if (!reduced.matches && (now - lastInput < 120 || Math.hypot(pointer.x - glow.x, pointer.y - glow.y) > 0.1)) {
        schedule();
      } else {
        sampleStart = samples = slow = last = 0;
      }
    }

    function paintHover(now: number, center: NonNullable<typeof glow>) {
      composite();
      ambientShown = false;
      paintGlyphs(ctx!, atlas!, width, height, ambientTime, {
        x: center.x - left,
        y: center.y - top,
        radius: CONFIG.radius * (stage >= 2 ? 0.75 : 1),
        time: reduced.matches ? 0 : now * 0.001 * CONFIG.speed,
      });
    }

    function schedule() {
      if (!frame && !paused()) frame = requestAnimationFrame(tick);
    }

    function leave() {
      pointer = glow = undefined;
      sampleStart = samples = slow = last = 0;
      cancelAnimationFrame(frame);
      frame = 0;
      if (!paused() && atlas && width && height) composite();
    }

    function move(event: PointerEvent) {
      if (paused() || event.pointerType === "touch") return;
      const { clientX: x, clientY: y } = event;
      if (x < left || y < top || x >= left + width || y >= top + height) return leave();
      pointer = { x, y };
      lastInput = performance.now();
      schedule();
    }

    function refreshStyle() {
      const { color, font } = readGlyphStyle(root);
      const key = `${color}|${font}|${dpr}`;
      if (key === styleKey || !color) return;
      styleKey = key;
      const request = ++fontRequest;
      void document.fonts.load(font, CONFIG.glyphs.join("")).then(() => {
        if (signal.aborted || request !== fontRequest) return;
        atlas = createAtlas(color, font, dpr);
        cache!.clearRect(0, 0, width, height);
        ambientShown = false;
        ambientIndices = undefined;
        refreshAmbient();
      }).catch(() => {
        if (!signal.aborted && request === fontRequest) styleKey = "";
      });
    }

    function measure() {
      layoutFrame = 0;
      if (paused()) return;
      const rect = region!.getBoundingClientRect();
      left = Math.max(0, rect.left);
      top = Math.max(0, rect.top);
      const w = Math.ceil(Math.min(innerWidth, rect.right) - left);
      const h = Math.ceil(Math.min(innerHeight, rect.bottom) - top);
      if (w <= 0 || h <= 0) return;
      const ratio = Math.min(devicePixelRatio || 1, 1.5);
      Object.assign(canvas!.style, { left: `${left}px`, top: `${top}px`, width: `${w}px`, height: `${h}px` });
      if (w === width && h === height && dpr === ratio && ambient.width === Math.ceil(w * dpr)) {
        if (pointer) schedule();
        return;
      }
      if (dpr !== ratio) atlas = undefined;
      dpr = ratio;
      width = w;
      height = h;
      canvas!.width = ambient.width = Math.ceil(w * dpr);
      canvas!.height = ambient.height = Math.ceil(h * dpr);
      ambientShown = false;
      ambientIndices = undefined;
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      cache!.setTransform(dpr, 0, 0, dpr, 0, 0);
      refreshStyle();
      refreshAmbient();
    }

    function queueMeasure() {
      if (!layoutFrame && !paused()) layoutFrame = requestAnimationFrame(measure);
    }

    function sync() {
      canvas!.hidden = disabled();
      leave();
      window.clearTimeout(timer);
      cancelAnimationFrame(layoutFrame);
      layoutFrame = 0;
      if (!paused()) {
        refreshStyle();
        queueMeasure();
        refreshAmbient();
      }
    }

    function trackResolution() {
      resolution?.removeEventListener("change", trackResolution);
      resolution = matchMedia(`(resolution: ${devicePixelRatio}dppx)`);
      resolution.addEventListener("change", trackResolution, { signal });
      queueMeasure();
    }

    const resize = new ResizeObserver(queueMeasure);
    resize.observe(region);
    const intersection = new IntersectionObserver(([entry]) => {
      visible = Boolean(entry?.isIntersecting);
      sync();
    });
    intersection.observe(region);
    const theme = new MutationObserver(() => {
      if (canvas.hidden !== disabled()) sync();
      else if (!paused()) refreshStyle();
    });
    theme.observe(root, {
      attributeFilter: ["class", "style", "data-theme", "data-cb", "data-contrast", "data-high-contrast", "data-effects", "data-shader"],
    });
    region.addEventListener("pointermove", move, { passive: true, signal });
    region.addEventListener("pointerdown", move, { passive: true, signal });
    region.addEventListener("pointerleave", leave, { signal });
    window.addEventListener("scroll", queueMeasure, { passive: true, capture: true, signal });
    window.addEventListener("resize", queueMeasure, { passive: true, signal });
    window.addEventListener("focus", sync, { signal });
    window.addEventListener("blur", sync, { signal });
    document.addEventListener("visibilitychange", sync, { signal });
    for (const query of [reduced, coarse, fine]) query.addEventListener("change", sync, { signal });
    contrast.addEventListener("change", refreshStyle, { signal });
    trackResolution();
    sync();
    return () => {
      listeners.abort();
      resize.disconnect();
      intersection.disconnect();
      theme.disconnect();
      cancelAnimationFrame(frame);
      cancelAnimationFrame(layoutFrame);
      window.clearTimeout(timer);
    };
  }, []);

  return <div className="wave-grid-layer" aria-hidden="true"><canvas ref={canvasRef} aria-hidden="true" /></div>;
}
