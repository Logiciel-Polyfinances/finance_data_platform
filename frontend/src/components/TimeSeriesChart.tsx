import { useMemo, useState, type CSSProperties } from "react";

export interface TsPoint {
  t: string; // ISO date
  v: number;
}

interface Props {
  data: TsPoint[];
  color: string;
  height?: number;
  fill?: boolean; // area from zero (e.g. drawdown) instead of a line
  fmt?: (v: number) => string;
  title?: string;
}

const W = 820; // viewBox width (px); the SVG scales to its container
const PAD = { l: 48, r: 12, t: 10, b: 22 };

// dark-theme chrome (the app UI is dark)
const MUTED = "#8b93a1";
const GRID = "#2a2e38";
const INK = "#e6e8ec";

const tip: CSSProperties = {
  position: "absolute",
  transform: "translate(-50%, 0)",
  background: "var(--panel)",
  border: "1px solid var(--border)",
  borderRadius: 6,
  padding: "4px 8px",
  fontSize: 12,
  pointerEvents: "none",
  whiteSpace: "nowrap",
  zIndex: 5,
};

function niceTicks(min: number, max: number, n = 4): number[] {
  if (min === max) return [min];
  const span = max - min;
  const step = Math.pow(10, Math.floor(Math.log10(span / n)));
  const err = (span / n) / step;
  const mult = err >= 7.5 ? 10 : err >= 3 ? 5 : err >= 1.5 ? 2 : 1;
  const s = mult * step;
  const start = Math.ceil(min / s) * s;
  const out: number[] = [];
  for (let x = start; x <= max + 1e-9; x += s) out.push(x);
  return out;
}

export default function TimeSeriesChart({ data, color, height = 300, fill, fmt, title }: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const f = fmt ?? ((v) => v.toFixed(2));

  const geom = useMemo(() => {
    if (data.length === 0) return null;
    const H = height;
    const vals = data.map((d) => d.v);
    let lo = Math.min(...vals);
    let hi = Math.max(...vals);
    if (fill) {
      hi = Math.max(0, hi);
      lo = Math.min(0, lo);
    }
    if (lo === hi) {
      lo -= 1;
      hi += 1;
    }
    const pad = (hi - lo) * 0.06;
    lo -= pad;
    hi += pad;

    const x = (i: number) => PAD.l + (i / Math.max(1, data.length - 1)) * (W - PAD.l - PAD.r);
    const y = (v: number) => PAD.t + (1 - (v - lo) / (hi - lo)) * (H - PAD.t - PAD.b);

    const line = data.map((d, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(d.v).toFixed(1)}`).join(" ");
    const area = fill ? `${line} L${x(data.length - 1).toFixed(1)},${y(0).toFixed(1)} L${x(0).toFixed(1)},${y(0).toFixed(1)} Z` : "";

    const yTicks = niceTicks(lo, hi).map((v) => ({ v, y: y(v) }));
    const step = Math.max(1, Math.floor((data.length - 1) / 5));
    const xTicks: { i: number; label: string }[] = [];
    for (let i = 0; i < data.length; i += step) xTicks.push({ i, label: data[i].t.slice(0, 7) });

    return { H, x, y, line, area, yTicks, xTicks };
  }, [data, height, fill]);

  if (!geom) return <div className="empty">No data.</div>;
  const { H, x, y, line, area, yTicks, xTicks } = geom;

  function onMove(e: React.MouseEvent<HTMLDivElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const frac = (e.clientX - rect.left) / rect.width;
    const px = frac * W;
    const i = Math.round(((px - PAD.l) / (W - PAD.l - PAD.r)) * (data.length - 1));
    setHover(Math.max(0, Math.min(data.length - 1, i)));
  }

  const hp = hover != null ? data[hover] : null;

  return (
    <div style={{ position: "relative" }} onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
      {title && <div className="muted" style={{ fontSize: 12, marginBottom: 2 }}>{title}</div>}
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
        {yTicks.map((t) => (
          <g key={t.v}>
            <line x1={PAD.l} x2={W - PAD.r} y1={t.y} y2={t.y} stroke={GRID} strokeWidth={1} />
            <text x={PAD.l - 6} y={t.y + 3} textAnchor="end" fontSize={10} fill={MUTED}>
              {f(t.v)}
            </text>
          </g>
        ))}
        {xTicks.map((t) => (
          <text key={t.i} x={x(t.i)} y={H - 6} textAnchor="middle" fontSize={10} fill={MUTED}>
            {t.label}
          </text>
        ))}
        {fill && <path d={area} fill={color} fillOpacity={0.85} />}
        {!fill && <path d={line} fill="none" stroke={color} strokeWidth={2} />}
        {hp && (
          <g>
            <line x1={x(hover!)} x2={x(hover!)} y1={PAD.t} y2={H - PAD.b} stroke={MUTED} strokeWidth={1} strokeDasharray="3 3" />
            <circle cx={x(hover!)} cy={y(hp.v)} r={3.5} fill={color} stroke="#fff" strokeWidth={1.5} />
          </g>
        )}
      </svg>
      {hp && (
        <div style={{ ...tip, left: `${(x(hover!) / W) * 100}%`, top: 8 }}>
          <span style={{ color: MUTED }}>{hp.t}</span>{"  "}
          <span style={{ color: INK, fontWeight: 600 }}>{f(hp.v)}</span>
        </div>
      )}
    </div>
  );
}
