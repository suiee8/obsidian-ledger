import { describe, expect, it, vi } from "vitest";

import { AuroraController } from "./controller";

function createHarness(options: {
  reducedMotion?: boolean;
  saveData?: boolean;
  draw?: () => void;
  getFrameTime?: () => number | null | undefined;
} = {}) {
  const canvas = new EventTarget();
  const callbacks = new Map<number, FrameRequestCallback>();
  const cancelled: number[] = [];
  let nextHandle = 0;
  let clock = 0;
  const visibilityListeners = new Set<EventListener>();
  const visibilityTarget = {
    hidden: false,
    addEventListener: (_type: "visibilitychange", listener: EventListener) => visibilityListeners.add(listener),
    removeEventListener: (_type: "visibilitychange", listener: EventListener) => visibilityListeners.delete(listener),
  };
  const draw = vi.fn(() => {
    options.draw?.();
  });
  const controller = new AuroraController({
    canvas,
    draw,
    getFrameTime: options.getFrameTime,
    visibilityTarget,
    now: () => clock,
    requestFrame: (callback) => {
      const handle = ++nextHandle;
      callbacks.set(handle, callback);
      return handle;
    },
    cancelFrame: (handle) => {
      cancelled.push(handle);
      callbacks.delete(handle);
    },
    reducedMotion: options.reducedMotion,
    saveData: options.saveData,
  });

  return {
    canvas,
    callbacks,
    cancelled,
    controller,
    draw,
    advanceClock: (milliseconds: number) => {
      clock += milliseconds;
    },
    setHidden: (hidden: boolean) => {
      visibilityTarget.hidden = hidden;
      for (const listener of visibilityListeners) listener(new Event("visibilitychange"));
    },
  };
}

describe("AuroraController", () => {
  it("pauses and resumes frames, then disposes its listeners and frame", () => {
    const harness = createHarness();
    harness.controller.start();
    expect(harness.callbacks.size).toBe(1);

    harness.controller.pause();
    expect(harness.callbacks.size).toBe(0);
    expect(harness.cancelled).toHaveLength(1);

    harness.controller.resume();
    expect(harness.callbacks.size).toBe(1);
    harness.controller.dispose();
    expect(harness.callbacks.size).toBe(0);
    expect(harness.cancelled).toHaveLength(2);
    harness.canvas.dispatchEvent(new Event("webglcontextlost", { cancelable: true }));
    expect(harness.controller.state.contextLost).toBe(false);
  });

  it("draws one static frame for reduced motion and resumes animation when it is disabled", () => {
    const harness = createHarness({ reducedMotion: true });
    harness.controller.start();
    expect(harness.draw).toHaveBeenCalledTimes(1);
    expect(harness.callbacks.size).toBe(0);

    harness.controller.setReducedMotion(false);
    expect(harness.callbacks.size).toBe(1);
    harness.controller.setReducedMotion(true);
    expect(harness.draw).toHaveBeenCalledTimes(2);
    expect(harness.callbacks.size).toBe(0);
    harness.controller.dispose();
  });

  it("pauses while the document is hidden and resumes when it becomes visible", () => {
    const harness = createHarness();
    harness.controller.start();
    harness.setHidden(true);
    expect(harness.controller.state.paused).toBe(true);
    expect(harness.callbacks.size).toBe(0);

    harness.setHidden(false);
    expect(harness.controller.state.paused).toBe(false);
    expect(harness.callbacks.size).toBe(1);
    harness.controller.dispose();
  });

  it("falls back and stops scheduling when the WebGL context is lost", () => {
    const harness = createHarness();
    harness.controller.start();
    const event = new Event("webglcontextlost", { cancelable: true });
    harness.canvas.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
    expect(harness.controller.state.contextLost).toBe(true);
    expect(harness.callbacks.size).toBe(0);
    harness.controller.dispose();
  });

  it("steps down scale, frame rate, and finally motion after 60 slow draws at each tier", () => {
    const harness = createHarness();
    harness.draw.mockImplementation(() => harness.advanceClock(13));
    let timestamp = 0;
    const driveDraws = (count: number) => {
      const initialCalls = harness.draw.mock.calls.length;
      while (harness.draw.mock.calls.length < initialCalls + count) {
        const entry = [...harness.callbacks.entries()][0];
        if (!entry) break;
        const [handle, callback] = entry;
        harness.callbacks.delete(handle);
        timestamp += 34;
        callback(timestamp);
      }
      return harness.draw.mock.calls.length - initialCalls;
    };

    harness.controller.start();
    expect(driveDraws(60)).toBe(60);
    expect(harness.controller.currentScale).toBe(0.25);
    expect(driveDraws(60)).toBe(60);
    expect(harness.controller.currentFrameRate).toBe(15);
    expect(driveDraws(60)).toBe(60);
    expect(harness.controller.state.motion).toBe("static");
    expect(harness.callbacks.size).toBe(0);
    harness.controller.dispose();
  });

  it("steps down from GPU timings even when CPU draw submission is fast", () => {
    const harness = createHarness({ getFrameTime: () => 13 });
    let timestamp = 0;
    const driveDraws = (count: number) => {
      const initialCalls = harness.draw.mock.calls.length;
      while (harness.draw.mock.calls.length < initialCalls + count) {
        const entry = [...harness.callbacks.entries()][0];
        if (!entry) break;
        const [handle, callback] = entry;
        harness.callbacks.delete(handle);
        timestamp += 34;
        callback(timestamp);
      }
      return harness.draw.mock.calls.length - initialCalls;
    };

    harness.controller.start();
    expect(driveDraws(60)).toBe(60);
    expect(harness.controller.currentScale).toBe(0.25);
    expect(driveDraws(60)).toBe(60);
    expect(harness.controller.currentFrameRate).toBe(15);
    expect(driveDraws(60)).toBe(60);
    expect(harness.controller.state.motion).toBe("static");
    expect(harness.callbacks.size).toBe(0);
    harness.controller.dispose();
  });
});
