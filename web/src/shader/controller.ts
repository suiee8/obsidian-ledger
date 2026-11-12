export interface AuroraFrame {
  elapsedMs: number;
  scale: number;
  pointer: { x: number; y: number };
}

export interface AuroraControllerState {
  motion: "animated" | "static";
  paused: boolean;
  contextLost: boolean;
}

interface VisibilityTarget {
  readonly hidden: boolean;
  addEventListener(type: "visibilitychange", listener: EventListener): void;
  removeEventListener(type: "visibilitychange", listener: EventListener): void;
}

interface AuroraControllerOptions {
  canvas: EventTarget;
  draw: (frame: AuroraFrame) => void;
  getFrameTime?: () => number | null | undefined;
  visibilityTarget?: VisibilityTarget;
  now?: () => number;
  requestFrame?: (callback: FrameRequestCallback) => number;
  cancelFrame?: (handle: number) => void;
  reducedMotion?: boolean;
  saveData?: boolean;
  onStateChange?: (state: AuroraControllerState) => void;
}

export class AuroraController {
  private readonly canvas: EventTarget;
  private readonly drawFrame: (frame: AuroraFrame) => void;
  private readonly getFrameTime?: () => number | null | undefined;
  private readonly visibilityTarget: VisibilityTarget;
  private readonly now: () => number;
  private readonly requestFrame: (callback: FrameRequestCallback) => number;
  private readonly cancelFrame: (handle: number) => void;
  private readonly onStateChange?: (state: AuroraControllerState) => void;
  private readonly onVisibilityChange = () => {
    if (this.visibilityTarget.hidden) this.pause();
    else this.resume();
  };
  private readonly onContextLost = (event: Event) => {
    event.preventDefault();
    this.contextLost = true;
    this.cancelScheduledFrame();
    this.notifyState();
  };

  private frameHandle: number | null = null;
  private started = false;
  private paused: boolean;
  private disposed = false;
  private reducedMotion: boolean;
  private saveData: boolean;
  private performanceStatic = false;
  private contextLost = false;
  private scale = 0.5;
  private frameRate = 30;
  private elapsedMs = 0;
  private previousTimestamp: number | null = null;
  private previousDrawTimestamp: number | null = null;
  private pointer = { x: 0, y: 0 };
  private pointerTarget = { x: 0, y: 0 };
  private readonly drawCosts: number[] = [];
  private framesInWindow = 0;

  constructor(options: AuroraControllerOptions) {
    this.canvas = options.canvas;
    this.drawFrame = options.draw;
    this.getFrameTime = options.getFrameTime;
    this.visibilityTarget = options.visibilityTarget ?? document;
    this.now = options.now ?? (() => performance.now());
    this.requestFrame = options.requestFrame ?? ((callback) => requestAnimationFrame(callback));
    this.cancelFrame = options.cancelFrame ?? ((handle) => cancelAnimationFrame(handle));
    this.reducedMotion = options.reducedMotion ?? false;
    this.saveData = options.saveData ?? false;
    this.paused = this.visibilityTarget.hidden;
    this.onStateChange = options.onStateChange;

    this.canvas.addEventListener("webglcontextlost", this.onContextLost);
    this.visibilityTarget.addEventListener("visibilitychange", this.onVisibilityChange);
  }

  get state(): AuroraControllerState {
    return {
      motion: this.isStatic ? "static" : "animated",
      paused: this.paused,
      contextLost: this.contextLost,
    };
  }

  get currentScale(): number {
    return this.scale;
  }

  get currentFrameRate(): number {
    return this.frameRate;
  }

  get isStatic(): boolean {
    return this.reducedMotion || this.saveData || this.performanceStatic;
  }

  start(): void {
    if (this.disposed) return;
    this.started = true;
    this.notifyState();
    if (this.isStatic) this.drawOnce();
    else this.schedule();
  }

  pause(): void {
    if (this.disposed || this.paused) return;
    this.paused = true;
    this.cancelScheduledFrame();
    this.notifyState();
  }

  resume(): void {
    if (this.disposed || !this.started || !this.paused || this.contextLost) return;
    this.paused = false;
    this.notifyState();
    if (this.isStatic) this.drawOnce();
    else this.schedule();
  }

  setReducedMotion(reduced: boolean): void {
    if (this.reducedMotion === reduced || this.disposed) return;
    this.reducedMotion = reduced;
    this.updateMotionMode();
  }

  setSaveData(enabled: boolean): void {
    if (this.saveData === enabled || this.disposed) return;
    this.saveData = enabled;
    this.updateMotionMode();
  }

  setPointer(x: number, y: number): void {
    this.pointerTarget = { x: Math.max(-1, Math.min(1, x)), y: Math.max(-1, Math.min(1, y)) };
  }

  invalidate(): void {
    if (!this.started || this.disposed || this.contextLost || this.paused) return;
    if (this.isStatic) this.drawOnce();
    else this.schedule();
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.cancelScheduledFrame();
    this.canvas.removeEventListener("webglcontextlost", this.onContextLost);
    this.visibilityTarget.removeEventListener("visibilitychange", this.onVisibilityChange);
  }

  private readonly onFrame: FrameRequestCallback = (timestamp) => {
    this.frameHandle = null;
    if (!this.started || this.paused || this.disposed || this.contextLost || this.isStatic) return;

    const elapsed = this.previousTimestamp === null ? 0 : Math.max(0, timestamp - this.previousTimestamp);
    this.previousTimestamp = timestamp;
    this.elapsedMs += elapsed;

    const interval = 1000 / this.frameRate;
    if (this.previousDrawTimestamp === null || timestamp - this.previousDrawTimestamp >= interval) {
      this.previousDrawTimestamp = timestamp;
      this.pointer.x += (this.pointerTarget.x - this.pointer.x) * 0.035;
      this.pointer.y += (this.pointerTarget.y - this.pointer.y) * 0.035;
      const start = this.now();
      this.drawFrame({ elapsedMs: this.elapsedMs, scale: this.scale, pointer: this.pointer });
      const cpuFrameTime = Math.max(0, this.now() - start);
      const measuredFrameTime = this.getFrameTime?.();
      if (measuredFrameTime === undefined) this.drawCosts.push(cpuFrameTime);
      else if (measuredFrameTime !== null) this.drawCosts.push(Math.max(0, measuredFrameTime));
      this.framesInWindow += 1;
      if (this.framesInWindow === 60) {
        this.framesInWindow = 0;
        this.stepDownIfNeeded();
      }
    }

    this.schedule();
  };

  private schedule(): void {
    if (
      this.frameHandle !== null ||
      !this.started ||
      this.paused ||
      this.disposed ||
      this.contextLost ||
      this.isStatic
    ) {
      return;
    }
    this.frameHandle = this.requestFrame(this.onFrame);
  }

  private drawOnce(): void {
    if (!this.started || this.disposed || this.paused || this.contextLost) return;
    this.drawFrame({ elapsedMs: this.elapsedMs, scale: this.scale, pointer: this.pointer });
  }

  private cancelScheduledFrame(): void {
    if (this.frameHandle === null) return;
    this.cancelFrame(this.frameHandle);
    this.frameHandle = null;
  }

  private updateMotionMode(): void {
    this.cancelScheduledFrame();
    this.notifyState();
    if (this.isStatic) this.drawOnce();
    else this.schedule();
  }

  private stepDownIfNeeded(): void {
    if (this.drawCosts.length === 0) return;
    const average = this.drawCosts.reduce((total, cost) => total + cost, 0) / this.drawCosts.length;
    this.drawCosts.length = 0;
    if (average <= 12) return;

    if (this.scale > 0.25) this.scale = 0.25;
    else if (this.frameRate > 15) this.frameRate = 15;
    else this.performanceStatic = true;

    this.notifyState();
    if (this.isStatic) this.cancelScheduledFrame();
  }

  private notifyState(): void {
    this.onStateChange?.(this.state);
  }
}
