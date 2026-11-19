import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

const TIP_X = 3;
const TIP_Y = 2;
const TRAIL_MS = 130;
const PULSE_MS = 220;
const NATIVE = "input, textarea, select, [contenteditable], [role='separator'], .resize-handle, .coach-resize, :disabled, [aria-disabled='true']";
const INTERACTIVE = "button, a[href], [role='button']";

type Point = { x: number; y: number; time: number };

export function CursorEffects() {
  const cursorRef = useRef<HTMLDivElement>(null);
  const arrowRef = useRef<HTMLSpanElement>(null);
  const pulseRef = useRef<HTMLSpanElement>(null);
  const trailRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const cursor = cursorRef.current;
    const arrow = arrowRef.current;
    const pulse = pulseRef.current;
    const trail = trailRef.current;
    if (!cursor || !arrow || !pulse || !trail) return;
    const root = document.documentElement;
    const motion = matchMedia("(prefers-reduced-motion: reduce)");
    const mouse = matchMedia("(any-pointer: fine)");
    const ctx = trail.getContext("2d");
    const trailColor = getComputedStyle(root).getPropertyValue("--white-24").trim();
    let frame = 0;
    let lastFrame = 0;
    let previous: Point | undefined;
    let enabled = false;
    let failed = false;
    let pressed = false;
    let hovering = false;
    let tilt = 0;
    let turn = 0;
    let scale = 1;
    let spring = 0;
    let velocity = 0;
    let angle = 0;
    let pulseTime = -Infinity;
    const points: Point[] = [];
    let dirty: { left: number; top: number; right: number; bottom: number } | undefined;

    const clearTrail = () => {
      if (!dirty) return;
      const { left, top, right, bottom } = dirty;
      ctx?.clearRect(left - 3, top - 3, right - left + 6, bottom - top + 6);
      dirty = undefined;
    };

    const restore = () => {
      delete root.dataset.ledgerCursor;
      cursor.hidden = true;
      pulse.hidden = true;
      previous = undefined;
      pressed = false;
      lastFrame = 0;
      pulseTime = -Infinity;
      points.length = 0;
      clearTrail();
      cancelAnimationFrame(frame);
      frame = 0;
    };
    const guard = (action: () => void) => {
      if (failed) return;
      try {
        action();
      } catch {
        failed = true;
        restore();
      }
    };

    const update = (now: number) => {
      guard(() => {
        frame = 0;
        const step = Math.min(2, Math.max(0.25, (now - (lastFrame || now - 16)) / 16));
        lastFrame = now;
        velocity *= 0.72 ** step;
        const nextTilt = Math.cos(angle) * Math.min(14, velocity * 7);
        turn = (turn + (nextTilt - tilt) * 0.24 * step) * 0.65 ** step;
        tilt += turn * step;
        const targetScale = pressed ? 0.88 : hovering ? 1.12 : 1;
        spring = (spring + (targetScale - scale) * 0.32 * step) * 0.65 ** step;
        scale += spring * step;
        const stretch = 1 + Math.min(0.12, velocity * 0.056);
        arrow.style.transform = `rotate(${Math.max(-14, Math.min(14, tilt))}deg) scale(${scale}) rotate(${angle}rad) scaleX(${stretch}) rotate(${-angle}rad)`;

        const age = now - pulseTime;
        const pulsing = age < PULSE_MS;
        if (pulse.hidden === pulsing) pulse.hidden = !pulsing;
        if (pulsing) {
          const progress = Math.max(0, age / PULSE_MS);
          pulse.style.transform = `scale(${0.35 + progress * 1.65})`;
          pulse.style.opacity = String(1 - progress);
        }
        while (points[0] && now - points[0].time >= TRAIL_MS) points.shift();
        clearTrail();
        const first = points[0];
        const latest = points[points.length - 1];
        if (ctx && first && latest && first !== latest) {
          const bounds = { left: first.x, top: first.y, right: first.x, bottom: first.y };
          ctx.globalAlpha = Math.max(0, Math.min(1, 1 - (now - latest.time) / TRAIL_MS));
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(first.x, first.y);
          for (const point of points) {
            ctx.lineTo(point.x, point.y);
            bounds.left = Math.min(bounds.left, point.x);
            bounds.top = Math.min(bounds.top, point.y);
            bounds.right = Math.max(bounds.right, point.x);
            bounds.bottom = Math.max(bounds.bottom, point.y);
          }
          ctx.stroke();
          dirty = bounds;
        }
        if (
          Math.abs(tilt) + Math.abs(turn) > 0.04 ||
          Math.abs(scale - targetScale) + Math.abs(spring) > 0.001 ||
          velocity > 0.02 || !pulse.hidden || points.length > 0
        ) schedule();
        else lastFrame = 0;
      });
    };
    function schedule() {
      if (!frame) frame = requestAnimationFrame(update);
    }

    const resize = () => {
      if (!ctx || !enabled) return;
      const canvasWidth = window.innerWidth;
      const canvasHeight = window.innerHeight;
      const density = Math.min(devicePixelRatio, 2);
      trail.width = Math.ceil(canvasWidth * density);
      trail.height = Math.ceil(canvasHeight * density);
      ctx.scale(density, density);
      ctx.strokeStyle = trailColor;
      ctx.lineCap = "round";
    };
    const syncPreference = () => guard(() => {
      restore();
      enabled = mouse.matches && !motion.matches;
      trail.hidden = !enabled;
      resize();
    });
    const move = (event: PointerEvent) => guard(() => {
      const target = event.composedPath()[0];
      if (!enabled || event.pointerType !== "mouse" || !(target instanceof Element) || target.closest(NATIVE)) {
        if (!cursor.hidden) restore();
        return;
      }
      const point = { x: event.clientX, y: event.clientY, time: performance.now() };
      cursor.style.transform = `translate3d(${point.x - TIP_X}px,${point.y - TIP_Y}px,0)`;
      const predicted = event.getPredictedEvents?.().at(-1);
      if (previous) {
        const dx = (predicted?.clientX ?? point.x) - previous.x;
        const dy = (predicted?.clientY ?? point.y) - previous.y;
        if (dx || dy) {
          angle = Math.atan2(dy, dx);
          velocity = Math.min(3, Math.hypot(dx, dy) / Math.max(8, point.time - previous.time));
        }
      }
      hovering = Boolean(target.closest(INTERACTIVE));
      cursor.dataset.hover = String(hovering);
      points.push(point);
      if (points.length > 14) points.shift();
      previous = point;
      schedule();
      cursor.hidden = false;
      root.dataset.ledgerCursor = "active";
    });
    const press = (event: PointerEvent) => guard(() => {
      if (event.button !== 0 || event.pointerType !== "mouse" || cursor.hidden) return;
      pressed = true;
      schedule();
    });
    const release = () => guard(() => {
      if (!pressed) return;
      pressed = false;
      spring = 0.055;
      schedule();
    });
    const click = (event: MouseEvent) => guard(() => {
      if (cursor.hidden || event.detail === 0) return;
      pulseTime = performance.now();
      pulse.style.left = `${event.clientX}px`;
      pulse.style.top = `${event.clientY}px`;
      schedule();
    });
    const exit = (event: PointerEvent) => {
      if (!event.relatedTarget && !cursor.hidden) restore();
    };
    const safeResize = () => guard(resize);

    syncPreference();
    motion.addEventListener("change", syncPreference);
    mouse.addEventListener("change", syncPreference);
    window.addEventListener("pointermove", move, { passive: true });
    window.addEventListener("pointerdown", press, { passive: true });
    window.addEventListener("pointerup", release, { passive: true });
    window.addEventListener("pointercancel", restore);
    window.addEventListener("pointerout", exit, { passive: true });
    window.addEventListener("blur", restore);
    window.addEventListener("resize", safeResize, { passive: true });
    window.addEventListener("click", click, true);
    return () => {
      restore();
      trail.hidden = true;
      motion.removeEventListener("change", syncPreference);
      mouse.removeEventListener("change", syncPreference);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerdown", press);
      window.removeEventListener("pointerup", release);
      window.removeEventListener("pointercancel", restore);
      window.removeEventListener("pointerout", exit);
      window.removeEventListener("blur", restore);
      window.removeEventListener("resize", safeResize);
      window.removeEventListener("click", click, true);
    };
  }, []);

  // Coach is a sibling of the isolated shell, so the pointer must paint above both.
  return createPortal(
    <>
      <canvas ref={trailRef} className="cursor-trail" aria-hidden="true" hidden />
      <span ref={pulseRef} className="cursor-pulse" aria-hidden="true" hidden />
      <div ref={cursorRef} className="cursor-arrow" aria-hidden="true" hidden>
        <span ref={arrowRef} />
      </div>
    </>,
    document.body,
  );
}
