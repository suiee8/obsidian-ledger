interface TimerExtension {
  TIME_ELAPSED_EXT: number;
  GPU_DISJOINT_EXT: number;
}

interface TimerQueryContext {
  readonly QUERY_RESULT: number;
  readonly QUERY_RESULT_AVAILABLE: number;
  beginQuery(target: number, query: WebGLQuery): void;
  createQuery(): WebGLQuery | null;
  deleteQuery(query: WebGLQuery): void;
  endQuery(target: number): void;
  finish(): void;
  getExtension(name: string): unknown;
  getParameter(parameter: number): unknown;
  getQueryParameter(query: WebGLQuery, parameter: number): unknown;
}

const SYNC_PROBE_INTERVAL = 5;
const MAX_QUERY_AGE_FRAMES = 60;

export class GpuFrameTimer {
  private readonly extension: TimerExtension | null;
  private mode: "query" | "synchronous";
  private pendingQuery: WebGLQuery | null = null;
  private recording = false;
  private queryAgeFrames = 0;
  private frameCount = 0;
  private syncStart: number | null = null;
  private latestFrameTime: number | null = null;

  constructor(
    private readonly gl: TimerQueryContext,
    private readonly now: () => number = () => performance.now(),
  ) {
    this.extension = gl.getExtension("EXT_disjoint_timer_query_webgl2") as TimerExtension | null;
    this.mode = this.extension ? "query" : "synchronous";
  }

  beginFrame(): void {
    if (this.mode === "synchronous") {
      this.frameCount += 1;
      if (this.frameCount % SYNC_PROBE_INTERVAL === 0) this.syncStart = this.now();
      return;
    }

    this.pollQuery();
    if (this.mode !== "query" || this.pendingQuery) return;
    const query = this.gl.createQuery();
    if (!query || !this.extension) {
      this.mode = "synchronous";
      return;
    }
    this.pendingQuery = query;
    this.queryAgeFrames = 0;
    this.recording = true;
    this.gl.beginQuery(this.extension.TIME_ELAPSED_EXT, query);
  }

  endFrame(): void {
    if (this.recording && this.extension) {
      this.gl.endQuery(this.extension.TIME_ELAPSED_EXT);
      this.recording = false;
      return;
    }
    if (this.mode === "synchronous" && this.syncStart !== null) {
      this.gl.finish();
      this.latestFrameTime = Math.max(0, this.now() - this.syncStart);
      this.syncStart = null;
    }
  }

  readFrameTime(): number | null {
    const result = this.latestFrameTime;
    this.latestFrameTime = null;
    return result;
  }

  dispose(): void {
    if (this.pendingQuery) this.gl.deleteQuery(this.pendingQuery);
    this.pendingQuery = null;
    this.recording = false;
  }

  private pollQuery(): void {
    const extension = this.extension;
    const query = this.pendingQuery;
    if (this.mode !== "query" || !extension || !query) return;

    if (!this.gl.getQueryParameter(query, this.gl.QUERY_RESULT_AVAILABLE)) {
      this.queryAgeFrames += 1;
      if (this.queryAgeFrames > MAX_QUERY_AGE_FRAMES) this.useSynchronousFallback();
      return;
    }

    const disjoint = this.gl.getParameter(extension.GPU_DISJOINT_EXT) === true;
    const nanoseconds = this.gl.getQueryParameter(query, this.gl.QUERY_RESULT);
    this.gl.deleteQuery(query);
    this.pendingQuery = null;
    if (disjoint || typeof nanoseconds !== "number") {
      this.useSynchronousFallback();
      return;
    }
    this.latestFrameTime = nanoseconds / 1_000_000;
  }

  private useSynchronousFallback(): void {
    if (this.pendingQuery) this.gl.deleteQuery(this.pendingQuery);
    this.pendingQuery = null;
    this.recording = false;
    this.mode = "synchronous";
    this.frameCount = 0;
  }
}
