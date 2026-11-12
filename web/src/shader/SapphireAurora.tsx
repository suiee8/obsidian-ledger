import { useEffect, useRef, useState } from "react";

import { palette } from "../tokens";
import { AuroraController, type AuroraFrame, type AuroraControllerState } from "./controller";
import fragmentShader from "./fragment.glsl?raw";
import { GpuFrameTimer } from "./gpuTimer";

type ShaderColors = {
  background: [number, number, number];
  royal700: [number, number, number];
  royal500: [number, number, number];
  royal400: [number, number, number];
  royal300: [number, number, number];
  ice: [number, number, number];
};

interface AuroraRenderer {
  draw: (frame: AuroraFrame) => void;
  getFrameTime: () => number | null;
  setColors: (colors: ShaderColors) => void;
  dispose: () => void;
}

function parseCssColor(value: string): [number, number, number] | null {
  const hex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(value.trim());
  if (hex?.[1]) {
    const digits = hex[1].length === 3 ? [...hex[1]].map((digit) => digit + digit).join("") : hex[1];
    return [0, 2, 4].map((offset) => Number.parseInt(digits.slice(offset, offset + 2), 16) / 255) as [
      number,
      number,
      number,
    ];
  }
  const rgb = /^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$/i.exec(value.trim());
  if (!rgb) return null;
  return [1, 2, 3].map((index) => Number(rgb[index]) / 255) as [number, number, number];
}

function readShaderColors(): ShaderColors | null {
  const style = getComputedStyle(document.documentElement);
  const read = (name: string, fallback: string) => parseCssColor(style.getPropertyValue(name).trim() || fallback);
  const background = read("--palette-background", palette.background);
  const royal700 = read("--palette-royal700", palette.royal700);
  const royal500 = read("--palette-royal500", palette.royal500);
  const royal400 = read("--palette-royal400", palette.royal400);
  const royal300 = read("--palette-royal300", palette.royal300);
  const ice = read("--palette-ice", palette.ice);
  if (!background || !royal700 || !royal500 || !royal400 || !royal300 || !ice) return null;
  return { background, royal700, royal500, royal400, royal300, ice };
}

function compileShader(gl: WebGL2RenderingContext, type: number, source: string): WebGLShader | null {
  const shader = gl.createShader(type);
  if (!shader) return null;
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (gl.getShaderParameter(shader, gl.COMPILE_STATUS)) return shader;
  gl.deleteShader(shader);
  return null;
}

function createRenderer(canvas: HTMLCanvasElement, gl: WebGL2RenderingContext): AuroraRenderer | null {
  const vertexShader = compileShader(
    gl,
    gl.VERTEX_SHADER,
    `#version 300 es
    in vec2 aPosition;
    void main() {
      gl_Position = vec4(aPosition, 0.0, 1.0);
    }`,
  );
  const pixelShader = compileShader(gl, gl.FRAGMENT_SHADER, fragmentShader);
  if (!vertexShader || !pixelShader) {
    if (vertexShader) gl.deleteShader(vertexShader);
    if (pixelShader) gl.deleteShader(pixelShader);
    return null;
  }

  const program = gl.createProgram();
  if (!program) {
    gl.deleteShader(vertexShader);
    gl.deleteShader(pixelShader);
    return null;
  }
  gl.attachShader(program, vertexShader);
  gl.attachShader(program, pixelShader);
  gl.linkProgram(program);
  gl.deleteShader(vertexShader);
  gl.deleteShader(pixelShader);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    gl.deleteProgram(program);
    return null;
  }

  const position = gl.getAttribLocation(program, "aPosition");
  const uniforms = {
    resolution: gl.getUniformLocation(program, "uResolution"),
    pointer: gl.getUniformLocation(program, "uPointer"),
    time: gl.getUniformLocation(program, "uTime"),
    background: gl.getUniformLocation(program, "uBackground"),
    royal700: gl.getUniformLocation(program, "uRoyal700"),
    royal500: gl.getUniformLocation(program, "uRoyal500"),
    royal400: gl.getUniformLocation(program, "uRoyal400"),
    royal300: gl.getUniformLocation(program, "uRoyal300"),
    ice: gl.getUniformLocation(program, "uIce"),
  };
  const { resolution, pointer, time, background, royal700, royal500, royal400, royal300, ice } = uniforms;
  if (
    position < 0 ||
    !resolution ||
    !pointer ||
    !time ||
    !background ||
    !royal700 ||
    !royal500 ||
    !royal400 ||
    !royal300 ||
    !ice
  ) {
    gl.deleteProgram(program);
    return null;
  }

  const buffer = gl.createBuffer();
  if (!buffer) {
    gl.deleteProgram(program);
    return null;
  }
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  gl.useProgram(program);
  gl.enableVertexAttribArray(position);
  gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);

  const initialColors = readShaderColors();
  if (!initialColors) {
    gl.deleteBuffer(buffer);
    gl.deleteProgram(program);
    return null;
  }
  let colors = initialColors;
  let width = 0;
  let height = 0;
  const timer = new GpuFrameTimer(gl);

  const setColors = (next: ShaderColors) => {
    colors = next;
  };
  const draw = (frame: AuroraFrame) => {
    const bounds = canvas.getBoundingClientRect();
    const nextWidth = Math.max(1, Math.floor(bounds.width * frame.scale));
    const nextHeight = Math.max(1, Math.floor(bounds.height * frame.scale));
    if (nextWidth !== width || nextHeight !== height) {
      width = nextWidth;
      height = nextHeight;
      canvas.width = width;
      canvas.height = height;
      gl.viewport(0, 0, width, height);
    }
    gl.useProgram(program);
    gl.uniform2f(resolution, width, height);
    gl.uniform2f(pointer, frame.pointer.x, frame.pointer.y);
    gl.uniform1f(time, frame.elapsedMs / 1000);
    gl.uniform3fv(background, colors.background);
    gl.uniform3fv(royal700, colors.royal700);
    gl.uniform3fv(royal500, colors.royal500);
    gl.uniform3fv(royal400, colors.royal400);
    gl.uniform3fv(royal300, colors.royal300);
    gl.uniform3fv(ice, colors.ice);
    timer.beginFrame();
    try {
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    } finally {
      timer.endFrame();
    }
  };

  return {
    draw,
    getFrameTime: () => timer.readFrameTime(),
    setColors,
    dispose: () => {
      timer.dispose();
      gl.deleteBuffer(buffer);
      gl.deleteProgram(program);
    },
  };
}

function saveDataEnabled(): boolean {
  const connection = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection;
  return connection?.saveData === true;
}

export default function SapphireAurora() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [fallback, setFallback] = useState(false);
  const [renderState, setRenderState] = useState<"pending" | "animated" | "static" | "fallback">("pending");
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    if (document.documentElement.dataset.shader === "off") {
      setFallback(true);
      setRenderState("fallback");
      return;
    }

    const gl = canvas.getContext("webgl2", {
      alpha: false,
      antialias: false,
      powerPreference: "low-power",
    });
    if (!gl) {
      setFallback(true);
      setRenderState("fallback");
      return;
    }

    const renderer = createRenderer(canvas, gl);
    if (!renderer) {
      setFallback(true);
      setRenderState("fallback");
      return;
    }

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const controller = new AuroraController({
      canvas,
      draw: renderer.draw,
      getFrameTime: renderer.getFrameTime,
      reducedMotion: reducedMotion.matches,
      saveData: saveDataEnabled(),
      onStateChange: (state: AuroraControllerState) => {
        setRenderState(state.contextLost ? "fallback" : state.motion);
        setFallback(state.contextLost);
        setPaused(state.paused);
      },
    });
    const refreshColors = () => {
      const colors = readShaderColors();
      if (colors) {
        renderer.setColors(colors);
        controller.invalidate();
      }
    };
    const observer = new MutationObserver(refreshColors);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "data-cb", "data-theme", "style"],
    });
    const mediaChange = () => controller.setReducedMotion(reducedMotion.matches);
    reducedMotion.addEventListener("change", mediaChange);
    const resize = () => controller.invalidate();
    const pointer = (event: PointerEvent) => {
      controller.setPointer((event.clientX / window.innerWidth) * 2 - 1, 1 - (event.clientY / window.innerHeight) * 2);
    };
    window.addEventListener("resize", resize);
    window.addEventListener("pointermove", pointer, { passive: true });
    controller.start();

    return () => {
      observer.disconnect();
      reducedMotion.removeEventListener("change", mediaChange);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", pointer);
      controller.dispose();
      renderer.dispose();
    };
  }, []);

  return (
    <div
      className="aurora-layer"
      aria-hidden="true"
      data-render-state={renderState}
      data-paused={paused ? "true" : "false"}
      data-fallback={fallback ? "true" : "false"}
    >
      <canvas ref={canvasRef} className="aurora-canvas" aria-hidden="true" />
    </div>
  );
}
