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
  AmbientLight,
  BoxGeometry,
  DirectionalLight,
  InstancedBufferAttribute,
  InstancedMesh,
  MathUtils,
  Matrix4,
  Mesh,
  MeshDepthMaterial,
  MeshPhongMaterial,
  OrthographicCamera,
  PCFShadowMap,
  PerspectiveCamera,
  Plane,
  PlaneGeometry,
  Raycaster,
  RGFormat,
  Scene,
  ShaderMaterial,
  Vector2,
  Vector3,
  Vector4,
  WebGLRenderer,
  WebGLRenderTarget,
} from "three";

const GRID_SIZE = 40;
const CUBE_WIDTH = 0.8;
const CUBE_HEIGHT = 3;
const SPACING = CUBE_WIDTH + 0.01;
const GRID_RADIUS = (GRID_SIZE * SPACING) / 2;
const MAX_TRAIL = 128;
const FADE_SECONDS = 2;
const TRAIL_LIFETIME = FADE_SECONDS * 4;
const IDLE_AFTER_MS = 3000;
const IDLE_INTERVAL_MS = 1500;
const MAX_RENDER_PIXELS = 500_000;
const CAMERA_EASE_MS = 360;
const RIPPLE_ATTACK_SECONDS = 0.06;

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
    vec2 worldXZ = cell + hash2(cell) * 0.2;
    float height = 0.0;
    float totalWeight = 0.0;
    for (int i = 0; i < uCount; i++) {
      vec4 source = uTrail[i];
      float dist = length(worldXZ - source.xy);
      float relativeDist = dist - 6.0 * source.z;
      // Beyond this distance the Gaussian contributes less than 0.002% of its peak.
      if (abs(relativeDist) > 10.0) continue;
      float windowWeight = exp(-(relativeDist * relativeDist) / 9.0);
      float weight = windowWeight * source.w / (1.0 + dist * 0.1);
      height += weight * cos(1.2 * relativeDist);
      totalWeight += weight;
    }
    float normalizedHeight = clamp(height / max(totalWeight, 1.0), -1.0, 1.0);
    // Store a 16-bit height across two channels to avoid visible displacement steps.
    float encodedHeight = floor((normalizedHeight * 0.5 + 0.5) * 65535.0 + 0.5);
    float highByte = floor(encodedHeight / 256.0);
    gl_FragColor = vec4(highByte / 255.0, (encodedHeight - highByte * 256.0) / 255.0, 0.0, 1.0);
  }
`;

const heightInput = /* glsl */ `
  attribute vec2 aCell;
  uniform sampler2D uHeights;
  varying float vWaveHeight;
`;

function displaceCubes(vertexShader: string) {
  return vertexShader
    .replace("#include <common>", `#include <common>\n${heightInput}`)
    .replace("#include <begin_vertex>", /* glsl */ `#include <begin_vertex>
      vWaveHeight = 0.0;
      if (position.y > 0.0) {
        vec2 heightBytes = texture2D(uHeights, aCell).rg;
        vWaveHeight = dot(heightBytes, vec2(65280.0, 255.0)) / 65535.0 * 2.0 - 1.0;
        transformed.y += vWaveHeight * 0.4;
      }`);
}

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
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = PCFShadowMap;

      const scene = new Scene();
      const ambient = new AmbientLight(0xffffff, 0.5);
      const key = new DirectionalLight(0xffffff, 4);
      key.position.set(-20, 10, 6);
      key.castShadow = true;
      key.shadow.mapSize.set(512, 512);
      key.shadow.radius = 3;
      key.shadow.bias = 0.0001;
      Object.assign(key.shadow.camera, { near: 0.1, far: 60, left: -22, right: 22, top: 22, bottom: -22 });
      key.shadow.camera.updateProjectionMatrix();
      const fill = new DirectionalLight(0xffffff, 1);
      fill.position.set(10, 5, -3);
      scene.add(ambient, key, fill);

      const camera = new PerspectiveCamera(40, 1, 0.1, 500);
      const pointer = new Vector2();
      const orbit = new Vector2();
      const raycaster = new Raycaster();
      const plane = new Plane(new Vector3(0, 1, 0), 0);
      const hit = new Vector3();
      const trail: Ripple[] = [];
      let previous: Ripple | undefined;
      let viewportWidth = 1;
      let viewportHeight = 1;
      let cameraRadius = 12;
      let frame = 0;
      let lastFrameTime: number | undefined;
      let idleTimer = 0;
      let contextLost = false;

      const heights = new WebGLRenderTarget(GRID_SIZE, GRID_SIZE, { format: RGFormat, depthBuffer: false });
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
      const material = new MeshPhongMaterial({ transparent: true });
      const resolution = new Vector2();
      material.onBeforeCompile = (shader) => {
        shader.uniforms.uHeights = { value: heights.texture };
        shader.uniforms.uResolution = { value: resolution };
        shader.vertexShader = displaceCubes(shader.vertexShader);
        shader.fragmentShader = shader.fragmentShader
          .replace("#include <common>", /* glsl */ `#include <common>
            varying float vWaveHeight;
            uniform vec2 uResolution;`)
          .replace("#include <opaque_fragment>", /* glsl */ `#include <opaque_fragment>
            float crest = clamp(vWaveHeight, 0.0, 1.0);
            float white = smoothstep(0.0, 0.55, crest);
            vec2 uv = gl_FragCoord.xy / uResolution;
            float vignette = 1.0 - 0.5 * smoothstep(0.3, 0.6, distance(uv, vec2(0.5)));
            vec3 shade = mix(min(gl_FragColor.rgb, vec3(1.0)) * 0.16, vec3(1.0), white);
            gl_FragColor = vec4(shade, mix(0.14, 1.0, white) * vignette);`);
      };
      const depthMaterial = new MeshDepthMaterial();
      depthMaterial.onBeforeCompile = (shader) => {
        shader.uniforms.uHeights = { value: heights.texture };
        shader.vertexShader = displaceCubes(shader.vertexShader);
      };
      const grid = new InstancedMesh(geometry, material, count);
      grid.castShadow = true;
      grid.receiveShadow = true;
      grid.customDepthMaterial = depthMaterial;
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

      function addRipple(point: Ripple) {
        if (trail.length === MAX_TRAIL) trail.shift();
        trail.push(point);
      }

      function scheduleIdle(delay: number) {
        window.clearTimeout(idleTimer);
        if (document.hidden || contextLost) return;
        idleTimer = window.setTimeout(() => {
          addRipple({
            x: (Math.random() - 0.5) * GRID_RADIUS,
            z: (Math.random() - 0.5) * GRID_RADIUS,
            born: performance.now(),
            distance: 0.8 + Math.random() * 0.2,
          });
          schedule();
          scheduleIdle(IDLE_INTERVAL_MS);
        }, delay);
      }

      function draw(now: number) {
        frame = 0;
        const elapsed = lastFrameTime === undefined ? 1000 / 60 : Math.min(now - lastFrameTime, 50);
        lastFrameTime = now;
        orbit.lerp(pointer, 1 - Math.exp(-elapsed / CAMERA_EASE_MS));
        positionCamera();

        while (trail[0] && (now - trail[0].born) / 1000 > TRAIL_LIFETIME) trail.shift();

        for (let i = 0; i < trail.length; i++) {
          const point = trail[i]!;
          const age = Math.max(0, (now - point.born) / 1000);
          const fade = MathUtils.smoothstep(age, 0, RIPPLE_ATTACK_SECONDS) * Math.exp(-age / FADE_SECONDS);
          uniforms.uTrail.value[i]!.set(point.x, point.z, age, point.distance * fade);
        }
        uniforms.uCount.value = trail.length;

        renderer.setRenderTarget(heights);
        renderer.render(heightScene, heightCamera);
        renderer.setRenderTarget(null);
        renderer.render(scene, camera);
        if (trail.length || orbit.distanceToSquared(pointer) > 0.000001) schedule();
        else lastFrameTime = undefined;
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
        renderer.getDrawingBufferSize(resolution);
        schedule();
      }

      function move(event: PointerEvent) {
        if (event.pointerType === "touch" || contextLost) return;
        pointer.set(
          (event.clientX / viewportWidth) * 2 - 1,
          1 - (event.clientY / viewportHeight) * 2,
        );
        schedule();
        raycaster.setFromCamera(pointer, camera);
        if (!raycaster.ray.intersectPlane(plane, hit) || Math.max(Math.abs(hit.x), Math.abs(hit.z)) > GRID_RADIUS) return;
        const distance = previous ? Math.hypot(hit.x - previous.x, hit.z - previous.z) : 0;
        if (previous && distance < 0.1) return;
        previous = { x: hit.x, z: hit.z, born: performance.now(), distance };
        addRipple(previous);
        scheduleIdle(IDLE_AFTER_MS + IDLE_INTERVAL_MS);
      }

      function leave() {
        pointer.set(0, 0);
        previous = undefined;
        schedule();
      }

      function onContextLost(event: Event) {
        event.preventDefault();
        contextLost = true;
        window.clearTimeout(idleTimer);
        cancelAnimationFrame(frame);
        frame = 0;
        canvas.hidden = true;
      }

      function onContextRestored() {
        contextLost = false;
        canvas.hidden = false;
        resize();
        scheduleIdle(IDLE_INTERVAL_MS);
      }

      function onVisibilityChange() {
        scheduleIdle(IDLE_INTERVAL_MS);
        schedule();
      }

      const observer = new ResizeObserver(resize);
      observer.observe(canvas);
      main.addEventListener("pointermove", move, { passive: true });
      main.addEventListener("pointerleave", leave);
      canvas.addEventListener("webglcontextlost", onContextLost);
      canvas.addEventListener("webglcontextrestored", onContextRestored);
      document.addEventListener("visibilitychange", onVisibilityChange);
      resize();
      scheduleIdle(IDLE_INTERVAL_MS);

      return () => {
        cancelAnimationFrame(frame);
        window.clearTimeout(idleTimer);
        observer.disconnect();
        main.removeEventListener("pointermove", move);
        main.removeEventListener("pointerleave", leave);
        canvas.removeEventListener("webglcontextlost", onContextLost);
        canvas.removeEventListener("webglcontextrestored", onContextRestored);
        document.removeEventListener("visibilitychange", onVisibilityChange);
        grid.dispose();
        geometry.dispose();
        material.dispose();
        depthMaterial.dispose();
        key.shadow.dispose();
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
