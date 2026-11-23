export const CONFIG = {
  glyphs: ["+", "=", "*"],
  cell: 24,
  fontSize: 15,
  baseAlpha: 0.1,
  hoverAlpha: 0.85,
  radius: 190,
  follow: 0.12,
  speed: 0.45,
  push: 5,
} as const;

export const influence = (distanceSquared: number, radius: number = CONFIG.radius) =>
  Math.exp((-2.2 * distanceSquared) / (radius * radius));

export const easing = (dt: number) => 1 - (1 - CONFIG.follow) ** (dt / 16.67);

export function glyphIndex(i: number, j: number, t: number, k = 0, hoverTime = t) {
  const n = Math.sin(i * 0.31 + t * 2.1)
    + Math.cos(j * 0.27 - t * 1.7)
    + Math.sin((i + j) * 0.14 + t * 1.1)
    + k * 1.6 * Math.sin(hoverTime * 6 + i * 0.5 - j * 0.5);
  const count = CONFIG.glyphs.length;
  return ((Math.floor((n + 3.2) * 0.9) % count) + count) % count;
}

export function readGlyphStyle(root: HTMLElement) {
  const style = getComputedStyle(root);
  return {
    color: style.getPropertyValue("--palette-white").trim(),
    font: `400 ${CONFIG.fontSize}px ${style.getPropertyValue("--font-mono").trim()}`,
  };
}

export const isPaused = (hidden: boolean, focused: boolean, visible: boolean, disabled: boolean) =>
  hidden || !focused || !visible || disabled;

const LEVELS = 24;
const SIZE = CONFIG.cell;

export function createAtlas(color: string, font: string, dpr: number) {
  const canvas = document.createElement("canvas");
  const tile = Math.round(CONFIG.fontSize * dpr);
  canvas.width = tile * CONFIG.glyphs.length;
  canvas.height = tile * LEVELS;
  const context = canvas.getContext("2d")!;
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
  context.font = font;
  context.fillStyle = color;
  context.textAlign = "center";
  context.textBaseline = "middle";
  for (let level = 0; level < LEVELS; level++) {
    context.globalAlpha = CONFIG.baseAlpha + CONFIG.hoverAlpha * level / (LEVELS - 1);
    CONFIG.glyphs.forEach((glyph, index) => {
      context.fillText(glyph, (index + 0.5) * tile / dpr, (level + 0.5) * tile / dpr);
    });
  }
  return (target: CanvasRenderingContext2D, index: number, k: number, x: number, y: number) =>
    target.drawImage(canvas, index * tile, Math.round(k * (LEVELS - 1)) * tile, tile, tile,
      x - tile / dpr / 2, y - tile / dpr / 2, tile / dpr, tile / dpr);
}

type Hover = { x: number; y: number; radius: number; time: number };

export function paintGlyphs(
  ctx: CanvasRenderingContext2D,
  sprite: ReturnType<typeof createAtlas>,
  width: number,
  height: number,
  t: number,
  hover?: Hover,
  indices?: Uint8Array,
  mirror?: CanvasRenderingContext2D,
) {
  const cols = Math.ceil(width / SIZE);
  const rows = Math.ceil(height / SIZE);
  const reach = hover ? hover.radius * Math.sqrt(-Math.log(0.01) / 2.2) : 0;
  const fromCol = hover ? Math.max(0, Math.floor((hover.x - reach) / SIZE)) : 0;
  const fromRow = hover ? Math.max(0, Math.floor((hover.y - reach) / SIZE)) : 0;
  const toCol = hover ? Math.min(cols, Math.ceil((hover.x + reach) / SIZE)) : cols;
  const toRow = hover ? Math.min(rows, Math.ceil((hover.y + reach) / SIZE)) : rows;
  const cells: { i: number; j: number; x: number; y: number; k: number }[] = [];
  for (let j = fromRow; j <= toRow; j++) {
    for (let i = fromCol; i <= toCol; i++) {
      const x = i * SIZE;
      const y = j * SIZE;
      if (!hover) {
        const index = glyphIndex(i, j, t);
        const offset = j * (cols + 1) + i;
        if (indices) {
          if (indices[offset] === index) continue;
          if (indices[offset] !== 255) {
            ctx.clearRect(x - SIZE / 2, y - SIZE / 2, SIZE, SIZE);
            mirror?.clearRect(x - SIZE / 2, y - SIZE / 2, SIZE, SIZE);
          }
          indices[offset] = index;
        }
        sprite(ctx, index, 0, x, y);
        if (mirror) sprite(mirror, index, 0, x, y);
        continue;
      }
      const dx = x - hover.x;
      const dy = y - hover.y;
      const distanceSquared = dx * dx + dy * dy;
      const k = influence(distanceSquared, hover.radius);
      if (k < 0.01) continue;
      const push = CONFIG.push * k / (Math.sqrt(distanceSquared) || 1);
      ctx.clearRect(x - SIZE / 2, y - SIZE / 2, SIZE, SIZE);
      cells.push({ i, j, k, x: x + dx * push, y: y + dy * push });
    }
  }
  for (const { i, j, k, x, y } of cells) sprite(ctx, glyphIndex(i, j, t, k, hover?.time), k, x, y);
}
