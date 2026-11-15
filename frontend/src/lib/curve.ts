export interface Point {
  x: number;
  y: number;
}

/** A smooth curve through the points (monotone cubic, so it never overshoots a peak or dips below a trough). */
export function smoothPath(points: Point[]): string {
  if (points.length === 0) return "";
  if (points.length === 1) return `M${points[0].x},${points[0].y}`;
  const n = points.length;
  const slope: number[] = [];
  const tangent: number[] = [];
  for (let i = 0; i < n - 1; i++) slope.push((points[i + 1].y - points[i].y) / (points[i + 1].x - points[i].x || 1));
  tangent.push(slope[0]);
  for (let i = 1; i < n - 1; i++) tangent.push(slope[i - 1] * slope[i] <= 0 ? 0 : (slope[i - 1] + slope[i]) / 2);
  tangent.push(slope[n - 2]);
  for (let i = 0; i < n - 1; i++) {
    if (slope[i] === 0) {
      tangent[i] = 0;
      tangent[i + 1] = 0;
      continue;
    }
    const a = tangent[i] / slope[i];
    const b = tangent[i + 1] / slope[i];
    const size = Math.hypot(a, b);
    if (size > 3) {
      tangent[i] = (3 * a * slope[i]) / size;
      tangent[i + 1] = (3 * b * slope[i]) / size;
    }
  }
  let path = `M${points[0].x},${points[0].y}`;
  for (let i = 0; i < n - 1; i++) {
    const dx = (points[i + 1].x - points[i].x) / 3;
    path += ` C${points[i].x + dx},${points[i].y + tangent[i] * dx} ${points[i + 1].x - dx},${points[i + 1].y - tangent[i + 1] * dx} ${points[i + 1].x},${points[i + 1].y}`;
  }
  return path;
}

/** Scales a series into a width × height box, with `pad` of breathing room all round. */
export function scale(values: number[], width: number, height: number, pad = 2, max?: number): Point[] {
  const top = max ?? Math.max(1, ...values);
  return values.map((value, index) => ({
    x: pad + (values.length === 1 ? (width - 2 * pad) / 2 : (index / (values.length - 1)) * (width - 2 * pad)),
    y: pad + (1 - value / top) * (height - 2 * pad),
  }));
}
