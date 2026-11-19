/* Wave motion adapted from VengeanceUI Wave Grid Background.
MIT License

Copyright (c) 2025-2026 Ashutoshx7

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
*/

import { useEffect, useRef } from "react";
import {
  BoxGeometry,
  InstancedBufferAttribute,
  InstancedMesh,
  MathUtils,
  Matrix4,
  Mesh,
  OrthographicCamera,
  PerspectiveCamera,
  Plane,
  PlaneGeometry,
  Raycaster,
  RedFormat,
  Scene,
  ShaderMaterial,
  Vector2,
  Vector3,
  Vector4,
  WebGLRenderer,
  WebGLRenderTarget,
} from "three";

const GRID_SIZE = 80;
const CUBE_WIDTH = 0.4;
const CUBE_HEIGHT = 1.5;
const SPACING = 0.405;
const GRID_RADIUS = (GRID_SIZE * SPACING) / 2;
// Halving a circle's area scales its radius by 1/√2. Stretch time to halve the outward speed too.
const WAVE_RADIUS_SCALE = Math.SQRT1_2;
const WAVE_SPEED_SCALE = 0.5;
const WAVE_TIME_SCALE = WAVE_RADIUS_SCALE / WAVE_SPEED_SCALE;
const MAX_TRAIL = 30;
const SAMPLE_INTERVAL_MS = 40 * WAVE_TIME_SCALE;
const TRAIL_LIFETIME = 1.15;
const MAX_RENDER_PIXELS = 500_000;

// Calculate one height per box, then share it with all its vertices.
const heightShader = /* glsl */ `
  uniform vec4 uTrail[${MAX_TRAIL}];
  uniform int uCount;

  vec2 hash2(vec2 p) {
    p = vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)));
    return fract(sin(p) * 43758.5453123) - 0.5;
  }

  void main() {
    vec2 cell = gl_FragCoord.xy * ${SPACING} - ${GRID_RADIUS.toFixed(3)};
    vec2 worldXZ = cell + hash2(cell) * 0.1;
    float height = 0.0;
    float totalWeight = 0.0;
    for (int i = 0; i < uCount; i++) {
      vec4 source = uTrail[i];
      float dist = length(worldXZ - source.xy) / ${WAVE_RADIUS_SCALE};
      float relativeDist = dist - 6.0 * source.z;
      if (abs(relativeDist) > 7.0) continue;
      float windowWeight = exp(-(relativeDist * relativeDist) / 9.0);
      float weight = windowWeight * source.w / (1.0 + dist * 0.1);
      height += weight * cos(1.2 * relativeDist);
      totalWeight += weight;
    }
    float normalizedHeight = clamp(height / max(totalWeight, 1.0), -1.0, 1.0);
    gl_FragColor = vec4(normalizedHeight * 0.5 + 0.5, 0.0, 0.0, 1.0);
  }
`;

const vertexShader = /* glsl */ `
  attribute vec2 aCell;
  uniform sampler2D uHeights;
  varying float vHeight;
  varying float vFace;

  void main() {
    vHeight = texture2D(uHeights, aCell).r * 2.0 - 1.0;
    if (vHeight <= 0.08) {
      gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
      return;
    }
    vFace = 0.65 + 0.35 * max(normal.y, 0.0);
    vec3 displaced = position;
    if (position.y > 0.0) displaced.y += vHeight * 0.2;
    gl_Position = projectionMatrix * modelViewMatrix * instanceMatrix * vec4(displaced, 1.0);
  }
`;

const fragmentShader = /* glsl */ `
  varying float vHeight;
  varying float vFace;

  void main() {
    float crest = smoothstep(0.08, 0.55, vHeight);
    gl_FragColor = vec4(1.0, 1.0, 1.0, crest * vFace);
  }
`;

type Ripple = { x: number; z: number; born: number; distance: number };

export default function WaveGridBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const main = canvas?.closest("main");
    if (!canvas || !main || document.documentElement.dataset.shader === "off") return;
    const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");

    function mount(canvas: HTMLCanvasElement, main: HTMLElement) {
      const context = canvas.getContext("webgl2", { alpha: true, antialias: false });
      if (!context) return;

      const renderer = new WebGLRenderer({ canvas, context, alpha: true, antialias: false });
      renderer.setClearColor(0x000000, 0);

      const scene = new Scene();
      const camera = new PerspectiveCamera(40, 1, 0.1, 500);
      const pointer = new Vector2();
      const orbit = new Vector2();
      const raycaster = new Raycaster();
      const plane = new Plane(new Vector3(0, 1, 0), 0);
      const hit = new Vector3();
      const trail: Ripple[] = [];
      let previous: Ripple | undefined;
      let pendingPoint = false;
      let viewportWidth = 1;
      let viewportHeight = 1;
      let cameraRadius = 12;
      let frame = 0;
      let lastDraw = 0;
      let contextLost = false;

      const heights = new WebGLRenderTarget(GRID_SIZE, GRID_SIZE, { format: RedFormat, depthBuffer: false });
      const heightScene = new Scene();
      const heightCamera = new OrthographicCamera(-1, 1, 1, -1, 0, 1);
      const heightGeometry = new PlaneGeometry(2, 2);
      const uniforms = {
        uTrail: { value: Array.from({ length: MAX_TRAIL }, () => new Vector4()) },
        uCount: { value: 0 },
      };
      const heightMaterial = new ShaderMaterial({
        uniforms,
        vertexShader: "void main() { gl_Position = vec4(position.xy, 0.0, 1.0); }",
        fragmentShader: heightShader,
        depthTest: false,
        depthWrite: false,
      });
      const heightPlane = new Mesh(heightGeometry, heightMaterial);
      heightPlane.frustumCulled = false;
      heightScene.add(heightPlane);

      const geometry = new BoxGeometry(CUBE_WIDTH, CUBE_HEIGHT, CUBE_WIDTH);
      const count = GRID_SIZE * GRID_SIZE;
      const cells = new InstancedBufferAttribute(new Float32Array(count * 2), 2);
      geometry.setAttribute("aCell", cells);
      const material = new ShaderMaterial({
        uniforms: { uHeights: { value: heights.texture } },
        vertexShader,
        fragmentShader,
        transparent: true,
      });
      const grid = new InstancedMesh(geometry, material, count);
      const transform = new Matrix4();
      const offset = ((GRID_SIZE - 1) * SPACING) / 2;
      for (let i = 0; i < count; i++) {
        const col = Math.floor(i / GRID_SIZE);
        const row = i % GRID_SIZE;
        const x = col * SPACING - offset;
        const z = row * SPACING - offset;
        grid.setMatrixAt(i, transform.makeTranslation(x, 0, z));
        cells.setXY(i, (col + 0.5) / GRID_SIZE, (row + 0.5) / GRID_SIZE);
      }
      scene.add(grid);

      function positionCamera() {
        const alpha = orbit.y * Math.PI * 0.03;
        const beta = orbit.x * Math.PI * 0.05;
        camera.position.set(
          -cameraRadius * Math.cos(alpha) * Math.sin(beta),
          cameraRadius * Math.cos(alpha) * Math.cos(beta),
          cameraRadius * Math.sin(alpha),
        );
        camera.up.set(0, 0, -1);
        camera.lookAt(0, 0, 0);
        camera.updateMatrixWorld();
      }

      function samplePointer(now: number) {
        if (!pendingPoint || (previous && now - previous.born < SAMPLE_INTERVAL_MS)) return;
        pendingPoint = false;
        raycaster.setFromCamera(pointer, camera);
        if (!raycaster.ray.intersectPlane(plane, hit) || Math.max(Math.abs(hit.x), Math.abs(hit.z)) > GRID_RADIUS) {
          previous = undefined;
          return;
        }
        const distance = previous ? Math.hypot(hit.x - previous.x, hit.z - previous.z) : 0.7;
        if (distance < 0.1) return;
        if (trail.length === MAX_TRAIL) trail.shift();
        previous = { x: hit.x, z: hit.z, born: now, distance: Math.min(distance, 3) };
        trail.push(previous);
      }

      function draw(now: number) {
        frame = 0;
        const elapsed = lastDraw ? now - lastDraw : 1000 / 60;
        lastDraw = now;
        orbit.lerp(pointer, 1 - Math.exp(-Math.min(elapsed, 50) / 140));
        positionCamera();
        samplePointer(now);

        while (trail[0] && (now - trail[0].born) / 1000 > TRAIL_LIFETIME * WAVE_TIME_SCALE) trail.shift();
        if (trail.length === 0) {
          renderer.clear();
          lastDraw = 0;
          if (pendingPoint) schedule();
          return;
        }

        for (let i = 0; i < trail.length; i++) {
          const point = trail[i]!;
          const age = (now - point.born) / (1000 * WAVE_TIME_SCALE);
          const fade = 1 - MathUtils.smoothstep(age, 0.55, TRAIL_LIFETIME);
          uniforms.uTrail.value[i]!.set(point.x, point.z, age, point.distance * fade);
        }
        uniforms.uCount.value = trail.length;

        renderer.setRenderTarget(heights);
        renderer.render(heightScene, heightCamera);
        renderer.setRenderTarget(null);
        renderer.render(scene, camera);
        schedule();
      }

      function schedule() {
        if (!frame && !contextLost && !document.hidden) frame = requestAnimationFrame(draw);
      }

      function resize() {
        viewportWidth = Math.max(1, canvas.clientWidth);
        viewportHeight = Math.max(1, canvas.clientHeight);
        const vertical = MathUtils.degToRad(camera.fov) / 2;
        camera.aspect = viewportWidth / viewportHeight;
        const horizontal = Math.atan(Math.tan(vertical) * camera.aspect);
        cameraRadius = Math.min(GRID_RADIUS / Math.tan(vertical), GRID_RADIUS / Math.tan(horizontal)) * 0.9
          + CUBE_HEIGHT * 0.5;
        camera.updateProjectionMatrix();
        positionCamera();
        // This layer is decorative. Cap its framebuffer independently of the display density.
        const scale = Math.min(0.75, Math.sqrt(MAX_RENDER_PIXELS / (viewportWidth * viewportHeight)));
        renderer.setDrawingBufferSize(viewportWidth, viewportHeight, scale);
        schedule();
      }

      function move(event: PointerEvent) {
        if (event.pointerType === "touch" || contextLost) return;
        pointer.set(
          (event.clientX / viewportWidth) * 2 - 1,
          1 - (event.clientY / viewportHeight) * 2,
        );
        pendingPoint = true;
        schedule();
      }

      function leave() {
        pointer.set(0, 0);
        previous = undefined;
        pendingPoint = false;
        schedule();
      }

      function onContextLost(event: Event) {
        event.preventDefault();
        contextLost = true;
        cancelAnimationFrame(frame);
        frame = 0;
        canvas.hidden = true;
      }

      function onContextRestored() {
        contextLost = false;
        canvas.hidden = false;
        resize();
      }

      const observer = new ResizeObserver(resize);
      observer.observe(canvas);
      main.addEventListener("pointermove", move, { passive: true });
      main.addEventListener("pointerleave", leave);
      canvas.addEventListener("webglcontextlost", onContextLost);
      canvas.addEventListener("webglcontextrestored", onContextRestored);
      document.addEventListener("visibilitychange", schedule);
      resize();

      return () => {
        cancelAnimationFrame(frame);
        observer.disconnect();
        main.removeEventListener("pointermove", move);
        main.removeEventListener("pointerleave", leave);
        canvas.removeEventListener("webglcontextlost", onContextLost);
        canvas.removeEventListener("webglcontextrestored", onContextRestored);
        document.removeEventListener("visibilitychange", schedule);
        grid.dispose();
        geometry.dispose();
        material.dispose();
        heightGeometry.dispose();
        heightMaterial.dispose();
        heights.dispose();
        renderer.dispose();
      };
    }

    let dispose: (() => void) | undefined;
    const applyMotion = () => {
      dispose?.();
      dispose = undefined;
      canvas.hidden = reducedMotion.matches;
      if (!reducedMotion.matches) dispose = mount(canvas, main);
    };
    applyMotion();
    reducedMotion.addEventListener("change", applyMotion);
    return () => {
      reducedMotion.removeEventListener("change", applyMotion);
      dispose?.();
    };
  }, []);

  return (
    <div className="wave-grid-layer" aria-hidden="true">
      <canvas ref={canvasRef} />
    </div>
  );
}
