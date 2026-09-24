import { useMemo, useState, type CSSProperties } from "react";

export interface BarSeries {
  name: string;
  color: string;
  values: (number | null)[]; // aligned with categories
}

interface Props {
  categories: string[];
  series: BarSeries[];
  height?: number;
  fmt?: (v: number) => string;
}

const W = 820;
const PAD = { l: 52, r: 12, t: 10, b: 44 };
// dark-theme chrome (the app UI is dark)
const MUTED = "#8b93a1";
const GRID = "#2a2e38";
const AXIS = "#3a3f4b";
const INK = "#e6e8ec";

const tip: CSSProperties = {
  position: "absolute",
  transform: "translate(-50%, 0)",
  background: "var(--panel)",
  border: "1px solid var(--border)",
  borderRadius: 6,
  padding: "6px 10px",
  fontSize: 12,
  pointerEvents: "none",
  whiteSpace: "nowrap",
  zIndex: 5,
};

export default function GroupedBarChart({ categories, series, height = 300, fmt }: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const f = fmt ?? ((v) => v.toFixed(2));

  const geom = useMemo(() => {
    const H = height;
    const all = series.flatMap((s) => s.values.filter((v): v is number => v != null));
    let lo = Math.min(0, ...(all.length ? all : [0]));
    let hi = Math.max(0, ...(all.length ? all : [1]));
    if (lo === hi) hi = lo + 1;
    const pad = (hi - lo) * 0.04;
    hi += pad;
    if (lo < 0) lo -= pad;

    const y = (v: number) => PAD.t + (1 - (v - lo) / (hi - lo)) * (H - PAD.t - PAD.b);
    const plotW = W - PAD.l - PAD.r;
    const groupW = plotW / Math.max(1, categories.length);
    const barW = (groupW * 0.7) / Math.max(1, series.length);
    const gx = (i: number) => PAD.l + i * groupW + groupW * 0.15;
    const ticks = [0, 0.25, 0.5, 0.75, 1].map((fr) => {
      const v = lo + fr * (hi - lo);
      return { v, y: y(v) };
    });
    return { H, y, y0: y(0), groupW, barW, gx, ticks };
  }, [categories, series, height]);

  const { H, y, y0, groupW, barW, gx, ticks } = geom;

  return (
    <div>
      <div className="row" style={{ gap: 14, marginBottom: 4 }}>
        {series.map((s) => (
          <span key={s.name} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
            <span style={{ width: 12, height: 12, background: s.color, borderRadius: 2, display: "inline-block" }} />
            {s.name}
          </span>
        ))}
      </div>
      <div style={{ position: "relative" }} onMouseLeave={() => setHover(null)}>
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
          {ticks.map((t) => (
            <g key={t.v}>
              <line x1={PAD.l} x2={W - PAD.r} y1={t.y} y2={t.y} stroke={GRID} strokeWidth={1} />
              <text x={PAD.l - 6} y={t.y + 3} textAnchor="end" fontSize={10} fill={MUTED}>
                {f(t.v)}
              </text>
            </g>
          ))}
          {/* zero baseline */}
          <line x1={PAD.l} x2={W - PAD.r} y1={y0} y2={y0} stroke={AXIS} strokeWidth={1} />
          {categories.map((c, i) => {
            const cx = gx(i) + (barW * series.length) / 2;
            return (
              <g key={c}>
                {series.map((s, j) => {
                  const v = s.values[i];
                  if (v == null) return null;
                  const x = gx(i) + j * barW;
                  return <rect key={s.name} x={x} y={Math.min(y0, y(v))} width={barW - 2} height={Math.abs(y(v) - y0)} fill={s.color} rx={2} />;
                })}
                <text x={cx} y={H - 6} textAnchor="middle" fontSize={9} fill={MUTED} transform={`rotate(30 ${cx} ${H - 6})`}>
                  {c}
                </text>
                <rect
                  x={PAD.l + i * groupW}
                  y={PAD.t}
                  width={groupW}
                  height={H - PAD.t - PAD.b}
                  fill={hover === i ? MUTED : "transparent"}
                  fillOpacity={hover === i ? 0.06 : 0}
                  onMouseEnter={() => setHover(i)}
                />
              </g>
            );
          })}
        </svg>
        {hover != null && (
          <div style={{ ...tip, left: `${((PAD.l + hover * groupW + groupW / 2) / W) * 100}%`, top: 6 }}>
            <div style={{ color: MUTED, marginBottom: 2 }}>{categories[hover]}</div>
            {series.map((s) => (
              <div key={s.name} style={{ color: INK }}>
                <span style={{ color: s.color }}>■</span> {s.name}: {s.values[hover] == null ? "—" : f(s.values[hover]!)}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
