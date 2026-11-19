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
  DataTexture,
  FloatType,
  InstancedBufferAttribute,
  InstancedMesh,
  MathUtils,
  Matrix4,
  PerspectiveCamera,
  Plane,
  Raycaster,
  RGBAFormat,
  Scene,
  ShaderMaterial,
  Vector2,
  Vector3,
  WebGLRenderer,
} from "three";

const GRID_SIZE = 40;
const CUBE_WIDTH = 0.8;
const CUBE_HEIGHT = 3;
const SPACING = CUBE_WIDTH + 0.01;
const MAX_TRAIL = 128;
const FADE_TIME = 2;
const TRAIL_LIFETIME = FADE_TIME * 4;

const vertexShader = /* glsl */ `
  attribute vec2 aOffset;
  uniform sampler2D uTrail;
  uniform int uCount;
  uniform float uFadeTime;
  varying float vHeight;
  varying float vFace;

  vec2 hash2(vec2 p) {
    p = vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)));
    return fract(sin(p) * 43758.5453123) - 0.5;
  }

  void main() {
    vec3 displaced = position;
    vHeight = 0.0;
    vFace = 0.65 + 0.35 * max(normal.y, 0.0);

    // The reference uses a cosine wave inside a moving Gaussian ring.
    if (position.y > 0.0) {
      vec2 worldXZ = aOffset + hash2(aOffset) * 0.2;
      float height = 0.0;
      float totalWeight = 0.0;
      for (int i = 0; i < uCount; i++) {
        vec4 source = texture2D(uTrail, vec2((float(i) + 0.5) / 128.0, 0.5));
        float dist = length(worldXZ - source.rg);
        float relativeDist = dist - 6.0 * source.b;
        float windowWeight = exp(-(relativeDist * relativeDist) / 9.0);
        float fade = exp(-source.b / uFadeTime);
        float attenuation = 1.0 / (1.0 + dist * 0.1);
        float weight = fade * windowWeight * attenuation * source.a;
        height += weight * cos(1.2 * relativeDist);
        totalWeight += weight;
      }
      vHeight = clamp(height / max(totalWeight, 1.0) * 0.4, -0.4, 0.4);
      displaced.y += vHeight;
    }

    gl_Position = projectionMatrix * modelViewMatrix * instanceMatrix * vec4(displaced, 1.0);
  }
`;

const fragmentShader = /* glsl */ `
  varying float vHeight;
  varying float vFace;

  void main() {
    float crest = smoothstep(0.015, 0.23, vHeight);
    float baseOpacity = 0.18 * vFace;
    float alpha = mix(baseOpacity, 1.0, crest);
    // Composite white over a faint dark grid. Solid crests are exactly white.
    vec3 base = vec3(0.02, 0.035, 0.08) * vFace;
    vec3 color = mix(base * baseOpacity, vec3(1.0), crest) / alpha;
    gl_FragColor = vec4(color, alpha);
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
      const context = canvas.getContext("webgl2", { alpha: true, antialias: true });
      if (!context) return;

      const renderer = new WebGLRenderer({ canvas, context, alpha: true, antialias: true });
      renderer.setClearColor(0x000000, 0);

      const scene = new Scene();
      const camera = new PerspectiveCamera(40, 1, 0.1, 500);
      const bounds = GRID_SIZE * SPACING;
      const pointer = new Vector2();
      const orbit = new Vector2();
      const raycaster = new Raycaster();
      const plane = new Plane(new Vector3(0, 1, 0), 0);
      const hit = new Vector3();
      const trail: Ripple[] = [];
      let previous: Ripple | undefined;
      let cameraRadius = 12;
      let frame = 0;
      let contextLost = false;

      const trailData = new Float32Array(MAX_TRAIL * 4);
      const texture = new DataTexture(trailData, MAX_TRAIL, 1, RGBAFormat, FloatType);
      texture.needsUpdate = true;
      const uniforms = { uTrail: { value: texture }, uCount: { value: 0 }, uFadeTime: { value: FADE_TIME } };
      const geometry = new BoxGeometry(CUBE_WIDTH, CUBE_HEIGHT, CUBE_WIDTH);
      const count = GRID_SIZE * GRID_SIZE;
      const offsets = new InstancedBufferAttribute(new Float32Array(count * 2), 2);
      geometry.setAttribute("aOffset", offsets);
      const material = new ShaderMaterial({ uniforms, vertexShader, fragmentShader, transparent: true });
      const grid = new InstancedMesh(geometry, material, count);
      const transform = new Matrix4();
      const offset = ((GRID_SIZE - 1) * SPACING) / 2;
      for (let i = 0; i < count; i++) {
        const x = Math.floor(i / GRID_SIZE) * SPACING - offset;
        const z = (i % GRID_SIZE) * SPACING - offset;
        grid.setMatrixAt(i, transform.makeTranslation(x, 0, z));
        offsets.setXY(i, x, z);
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

      function draw(now: number) {
        frame = 0;
        while (trail[0] && (now - trail[0].born) / 1000 > TRAIL_LIFETIME) trail.shift();
        for (let i = 0; i < trail.length; i++) {
          const point = trail[i]!;
          trailData[i * 4] = point.x;
          trailData[i * 4 + 1] = point.z;
          trailData[i * 4 + 2] = (now - point.born) / 1000;
          trailData[i * 4 + 3] = point.distance;
        }
        texture.needsUpdate = trail.length > 0;
        uniforms.uCount.value = trail.length;

        orbit.lerp(pointer, 0.04);
        positionCamera();
        renderer.render(scene, camera);
        if (trail.length || orbit.distanceToSquared(pointer) > 0.000001) schedule();
      }

      function schedule() {
        if (!frame && !contextLost && !document.hidden) frame = requestAnimationFrame(draw);
      }

      function resize() {
        const width = Math.max(1, canvas.clientWidth);
        const height = Math.max(1, canvas.clientHeight);
        const vertical = MathUtils.degToRad(camera.fov) / 2;
        camera.aspect = width / height;
        const horizontal = Math.atan(Math.tan(vertical) * camera.aspect);
        cameraRadius = Math.min(bounds / (2 * Math.tan(vertical)), bounds / (2 * Math.tan(horizontal))) * 0.9
          + CUBE_HEIGHT * 0.5;
        camera.updateProjectionMatrix();
        positionCamera();
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
        renderer.setSize(width, height, false);
        schedule();
      }

      function move(event: PointerEvent) {
        if (event.pointerType === "touch" || contextLost) return;
        const rect = canvas.getBoundingClientRect();
        if (!rect.width || !rect.height) return;
        pointer.set(
          ((event.clientX - rect.left) / rect.width) * 2 - 1,
          1 - ((event.clientY - rect.top) / rect.height) * 2,
        );
        raycaster.setFromCamera(pointer, camera);
        if (raycaster.ray.intersectPlane(plane, hit) && Math.max(Math.abs(hit.x), Math.abs(hit.z)) <= bounds / 2) {
          const distance = previous ? Math.hypot(hit.x - previous.x, hit.z - previous.z) : 0;
          if (!previous || distance >= 0.1) {
            if (trail.length === MAX_TRAIL) trail.shift();
            previous = { x: hit.x, z: hit.z, born: performance.now(), distance };
            trail.push(previous);
          }
        }
        schedule();
      }

      function leave() {
        pointer.set(0, 0);
        previous = undefined;
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
        texture.dispose();
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
