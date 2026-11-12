#version 300 es
precision highp float;

uniform vec2 uResolution;
uniform vec2 uPointer;
uniform float uTime;
uniform vec3 uBackground;
uniform vec3 uRoyal700;
uniform vec3 uRoyal500;
uniform vec3 uRoyal400;
uniform vec3 uRoyal300;
uniform vec3 uIce;

out vec4 outColor;

float hash21(vec2 point) {
  point = fract(point * vec2(123.34, 456.21));
  point += dot(point, point + 45.32);
  return fract(point.x * point.y);
}

float noise2(vec2 point) {
  vec2 cell = floor(point);
  vec2 local = fract(point);
  local = local * local * (3.0 - 2.0 * local);
  float a = hash21(cell);
  float b = hash21(cell + vec2(1.0, 0.0));
  float c = hash21(cell + vec2(0.0, 1.0));
  float d = hash21(cell + vec2(1.0, 1.0));
  return mix(mix(a, b, local.x), mix(c, d, local.x), local.y);
}

void main() {
  vec2 uv = gl_FragCoord.xy / uResolution;
  vec2 point = uv - 0.5;
  point.x *= uResolution.x / uResolution.y;
  point += uPointer * 0.018;

  float time = uTime * 0.035;
  float warp = noise2(point * 2.8 + vec2(time, -time * 0.7)) - 0.5;
  float flow = point.y + sin(point.x * 2.4 + warp * 2.5 + time) * 0.11;
  float ribbonA = exp(-abs(flow + 0.08) * 44.0);
  float ribbonB = exp(-abs(flow - 0.11 + warp * 0.07) * 64.0) * 0.68;
  float ribbons = clamp(ribbonA + ribbonB, 0.0, 1.0);

  float vignette = 1.0 - smoothstep(0.12, 0.92, length(point * vec2(0.62, 0.9)));
  vec3 base = mix(uBackground, uRoyal700, (0.035 + warp * 0.025) * vignette);
  vec3 ribbonColor = mix(uRoyal500, uRoyal400, smoothstep(0.0, 0.22, ribbonA));
  ribbonColor = mix(ribbonColor, uRoyal300, smoothstep(0.08, 0.28, ribbonA));
  ribbonColor = mix(ribbonColor, uIce, smoothstep(0.66, 0.96, ribbons) * 0.24);
  vec3 color = mix(base, ribbonColor, ribbons * vignette * 0.56);

  float grain = hash21(gl_FragCoord.xy) - 0.5;
  color += uIce * grain * 0.012;
  color = mix(uBackground, color, vignette);
  outColor = vec4(color, 1.0);
}
