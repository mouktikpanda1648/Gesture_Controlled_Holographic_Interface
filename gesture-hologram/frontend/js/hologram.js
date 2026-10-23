/**
 * Pepper's-ghost compositor.
 *
 * A truncated transparent pyramid (small end down) sits on the screen centre.
 * Each of its four faces reflects the screen area in front of it.  Seen via the
 * reflection, the part of the image farther from the pyramid appears *higher*,
 * so every copy is drawn vertically flipped, then rotated to face its side.
 */
export function drawHologram(ctx, w, h, scene, { scale, gap, guide }) {
  const m = Math.min(w, h);
  const cell = m * scale;
  const off = m * gap;
  const cx = w / 2, cy = h / 2;

  for (let k = 0; k < 4; k++) {
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate((k * Math.PI) / 2);
    ctx.translate(0, off + cell / 2);
    ctx.scale(1, -1);
    ctx.drawImage(scene, -cell / 2, -cell / 2, cell, cell);
    ctx.restore();
  }

  if (guide) drawGuide(ctx, cx, cy, cell, off);
}

function drawGuide(ctx, cx, cy, cell, off) {
  ctx.save();
  ctx.translate(cx, cy);
  ctx.strokeStyle = 'rgba(255,255,255,.45)';
  ctx.fillStyle = 'rgba(255,255,255,.7)';
  ctx.lineWidth = 1;
  ctx.setLineDash([6, 6]);

  // pyramid footprint (small base) and the four image cells
  ctx.strokeRect(-off, -off, off * 2, off * 2);
  for (let k = 0; k < 4; k++) {
    ctx.save();
    ctx.rotate((k * Math.PI) / 2);
    ctx.strokeRect(-cell / 2, off, cell, cell);
    ctx.restore();
  }
  ctx.setLineDash([]);
  ctx.beginPath();
  ctx.moveTo(-14, 0); ctx.lineTo(14, 0);
  ctx.moveTo(0, -14); ctx.lineTo(0, 14);
  ctx.stroke();
  ctx.font = '12px ui-monospace, Consolas, monospace';
  ctx.textAlign = 'center';
  ctx.fillText('PYRAMID BASE', 0, -off - 10);
  ctx.restore();
}
