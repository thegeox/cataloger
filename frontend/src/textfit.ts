// Mirrors layout_text() in backend/app/services/renderer.py so the editor canvas
// shows the same auto-shrunk font size the server will render.
import type { TextElement } from "./types";

let ctx: CanvasRenderingContext2D | null = null;

function wrapCount(text: string, maxWidth: number, measure: (s: string) => number): { lines: number; widest: number } {
  let lines = 0;
  let widest = 0;
  for (const paragraph of text.split("\n")) {
    let current = "";
    for (const word of paragraph.split(" ")) {
      widest = Math.max(widest, measure(word));
      const candidate = current ? `${current} ${word}` : word;
      if (measure(candidate) <= maxWidth || !current) current = candidate;
      else {
        lines++;
        current = word;
      }
    }
    lines++;
  }
  return { lines, widest };
}

export function fitFontSize(el: TextElement, text: string, fontFamilyCss: string): number {
  let size = Math.max(4, Math.round(el.font_size));
  if (!el.auto_shrink || !text.trim()) return size;
  ctx ??= document.createElement("canvas").getContext("2d");
  if (!ctx) return size;
  const innerW = Math.max(1, el.width - 2 * el.padding);
  const innerH = Math.max(1, el.height - 2 * el.padding);
  for (;;) {
    ctx.font = `${el.italic ? "italic " : ""}${el.bold ? "700 " : ""}${size}px ${fontFamilyCss}`;
    const { lines, widest } = wrapCount(text, innerW, (s) => ctx!.measureText(s).width);
    if ((lines * size * el.line_height <= innerH + 0.5 && widest <= innerW + 0.5) || size <= 6) return size;
    size = Math.max(6, Math.floor(size * 0.92));
  }
}
