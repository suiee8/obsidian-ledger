import { describe, expect, it, vi } from "vitest";

import { GpuFrameTimer } from "./gpuTimer";

function createContext(options: { extension?: boolean; disjoint?: boolean } = {}) {
  const query = {} as WebGLQuery;
  let available = false;
  let disjoint = options.disjoint ?? false;
  let clock = 0;
  const gl = {
    QUERY_RESULT: 1,
    QUERY_RESULT_AVAILABLE: 2,
    beginQuery: vi.fn(),
    createQuery: vi.fn(() => query),
    deleteQuery: vi.fn(),
    endQuery: vi.fn(),
    finish: vi.fn(),
    getExtension: vi.fn(() =>
      options.extension === false ? null : { TIME_ELAPSED_EXT: 3, GPU_DISJOINT_EXT: 4 },
    ),
    getParameter: vi.fn(() => disjoint),
    getQueryParameter: vi.fn((_query: WebGLQuery, parameter: number) =>
      parameter === gl.QUERY_RESULT_AVAILABLE ? available : 13_000_000,
    ),
  };
  const timer = new GpuFrameTimer(gl, () => clock);
  return {
    gl,
    timer,
    setAvailable: (value: boolean) => {
      available = value;
    },
    setDisjoint: (value: boolean) => {
      disjoint = value;
    },
    advanceClock: (milliseconds: number) => {
      clock += milliseconds;
    },
  };
}

describe("GpuFrameTimer", () => {
  it("reads elapsed GPU query results asynchronously in milliseconds", () => {
    const harness = createContext();
    harness.timer.beginFrame();
    harness.timer.endFrame();
    expect(harness.timer.readFrameTime()).toBeNull();

    harness.setAvailable(true);
    harness.timer.beginFrame();
    harness.timer.endFrame();

    expect(harness.timer.readFrameTime()).toBe(13);
    expect(harness.gl.deleteQuery).toHaveBeenCalledTimes(1);
    harness.timer.dispose();
  });

  it("discards disjoint GPU timings and switches to synchronous probes", () => {
    const harness = createContext({ disjoint: true });
    harness.timer.beginFrame();
    harness.timer.endFrame();
    harness.setAvailable(true);
    harness.timer.beginFrame();
    harness.timer.endFrame();

    expect(harness.timer.readFrameTime()).toBeNull();
    harness.setDisjoint(false);
    for (let frame = 0; frame < 5; frame += 1) {
      harness.timer.beginFrame();
      harness.advanceClock(13);
      harness.timer.endFrame();
    }

    expect(harness.gl.finish).toHaveBeenCalledTimes(1);
    expect(harness.timer.readFrameTime()).toBe(13);
    harness.timer.dispose();
  });

  it("uses periodic GPU-synchronized probes when timer queries are unavailable", () => {
    const harness = createContext({ extension: false });
    for (let frame = 0; frame < 4; frame += 1) {
      harness.timer.beginFrame();
      harness.advanceClock(13);
      harness.timer.endFrame();
    }
    expect(harness.gl.finish).not.toHaveBeenCalled();

    harness.timer.beginFrame();
    harness.advanceClock(13);
    harness.timer.endFrame();

    expect(harness.gl.finish).toHaveBeenCalledTimes(1);
    expect(harness.timer.readFrameTime()).toBe(13);
    harness.timer.dispose();
  });
});
