import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { api, errMsg } from "../api";
import type { InstrumentMetric, FundamentalRatio, Price, Fundamental } from "../types";
import TimeSeriesChart, { type TsPoint } from "./TimeSeriesChart";
import GroupedBarChart from "./GroupedBarChart";

interface TickerProps {
  apiKey: string;
  ticker: string;
}

// mirror of backend fundamentals_ratios.CONCEPTS (revenue / net_income)
const REVENUE = [
  "us-gaap:Revenues",
  "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
  "us-gaap:SalesRevenueNet",
];
const NETINCOME = ["us-gaap:NetIncomeLoss", "us-gaap:ProfitLoss"];

// dark-theme series steps (validated dark palette); status red is mode-invariant
const BLUE = "#3987e5";
const ORANGE = "#d95926";
const RED = "#d03b3b";

const dash = "—";
const pctRatio = (v: number | null) => (v == null ? dash : `${(v * 100).toFixed(2)}%`);
const pctRaw = (v: number | null) => (v == null ? dash : `${v.toFixed(2)}%`);
const num2 = (v: number | null) => (v == null ? dash : v.toFixed(2));
const moneyB = (v: number | null) => (v == null ? dash : `${(v / 1e9).toFixed(2)}B`);

type Tone = "pos" | "neg" | "loss" | "neutral";
interface Tile {
  label: string;
  value: string;
  tone?: Tone;
  raw?: number | null;
}
function toneColor(t: Tile): string {
  if (t.tone === "loss") return "var(--bad)";
  if (t.tone === "pos" || t.tone === "neg") {
    if (t.raw == null) return "var(--text)";
    return t.raw >= 0 ? "var(--ok)" : "var(--bad)";
  }
  return "var(--text)";
}

const TILE: CSSProperties = {
  background: "var(--panel)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: "10px 12px",
};
const GRID: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))",
  gap: 8,
  marginBottom: 18,
};

function TileGrid({ title, tiles }: { title: string; tiles: Tile[] }) {
  if (tiles.length === 0) return null;
  return (
    <section style={{ marginBottom: 6 }}>
      <div className="row">
        <strong>{title}</strong>
      </div>
      <div style={GRID}>
        {tiles.map((t) => (
          <div key={t.label} style={TILE}>
            <div className="muted" style={{ fontSize: 11 }}>{t.label}</div>
            <div style={{ fontSize: 18, fontWeight: 600, fontVariantNumeric: "tabular-nums", color: toneColor(t) }}>
              {t.value}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

const RANGES: [string, number][] = [
  ["1M", 30],
  ["3M", 90],
  ["6M", 182],
  ["1Y", 365],
  ["Max", 1e9],
];

function ChartPanel({ apiKey, ticker }: TickerProps) {
  const [prices, setPrices] = useState<Price[] | null>(null);
  const [range, setRange] = useState(365);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ticker) return;
    setPrices(null);
    setError(null);
    api<Price[]>(`/prices/${ticker}?limit=5000&order=asc`, apiKey)
      .then(setPrices)
      .catch((e) => setError(errMsg(e)));
  }, [apiKey, ticker]);

  const { line, drawdown } = useMemo(() => {
    if (!prices) return { line: [] as TsPoint[], drawdown: [] as TsPoint[] };
    const clean = prices.filter((p) => p.close != null) as (Price & { close: number })[];
    const cutoff = range >= 1e9 ? "" : new Date(Date.now() - range * 864e5).toISOString().slice(0, 10);
    const sliced = cutoff ? clean.filter((p) => p.ts >= cutoff) : clean;
    let peak = sliced[0]?.close ?? 0;
    const line: TsPoint[] = [];
    const drawdown: TsPoint[] = [];
    for (const p of sliced) {
      peak = Math.max(peak, p.close);
      line.push({ t: p.ts, v: p.close });
      drawdown.push({ t: p.ts, v: peak ? (p.close - peak) / peak : 0 });
    }
    return { line, drawdown };
  }, [prices, range]);

  return (
    <section style={{ marginBottom: 20 }}>
      <div className="row">
        <strong>Price &amp; drawdown</strong>
        <div className="tabs" style={{ marginBottom: 0, marginLeft: "auto" }}>
          {RANGES.map(([label, days]) => (
            <button key={label} className={range === days ? "active" : ""} onClick={() => setRange(days)}>
              {label}
            </button>
          ))}
        </div>
      </div>
      {error && <div className="empty">No prices: {error}</div>}
      {!error && !prices && <div className="empty">Loading chart...</div>}
      {!error && prices && line.length > 1 && (
        <>
          <TimeSeriesChart data={line} color={BLUE} height={280} fmt={(v) => v.toFixed(2)} />
          <TimeSeriesChart data={drawdown} color={RED} height={110} fill fmt={(v) => `${(v * 100).toFixed(2)}%`} title="Drawdown from peak" />
        </>
      )}
      {!error && prices && line.length <= 1 && <div className="empty">Not enough price history in range.</div>}
    </section>
  );
}

function FundamentalsChartPanel({ apiKey, ticker }: TickerProps) {
  const [rows, setRows] = useState<Fundamental[] | null>(null);

  useEffect(() => {
    if (!ticker) return;
    setRows(null);
    const qs = new URLSearchParams({ concepts: [...REVENUE, ...NETINCOME].join(","), period: "annual", limit: "2000", order: "asc" });
    api<Fundamental[]>(`/fundamentals/${ticker}?${qs}`, apiKey)
      .then(setRows)
      .catch(() => setRows([]));
  }, [apiKey, ticker]);

  const chart = useMemo(() => {
    if (!rows || rows.length === 0) return null;
    const lastPeriod = (concept: string) =>
      rows.filter((r) => r.concept === concept).reduce((mx, r) => (r.period_end > mx ? r.period_end : mx), "");
    const freshest = (cands: string[]) => {
      const present = cands.filter((c) => rows.some((r) => r.concept === c));
      if (present.length === 0) return null;
      return present.reduce((best, c) => (lastPeriod(c) > lastPeriod(best) ? c : best));
    };
    const revC = freshest(REVENUE);
    const niC = freshest(NETINCOME);
    const byPeriod = (concept: string | null) => {
      const m: Record<string, number> = {};
      if (concept) for (const r of rows) if (r.concept === concept) m[r.period_end] = r.val;
      return m;
    };
    const rev = byPeriod(revC);
    const ni = byPeriod(niC);
    const periods = [...new Set([...Object.keys(rev), ...Object.keys(ni)])].sort().slice(-8);
    if (periods.length === 0) return null;
    return {
      categories: periods,
      series: [
        { name: "Revenue", color: BLUE, values: periods.map((p) => (rev[p] != null ? rev[p] / 1e9 : null)) },
        { name: "Net income", color: ORANGE, values: periods.map((p) => (ni[p] != null ? ni[p] / 1e9 : null)) },
      ],
    };
  }, [rows]);

  return (
    <section style={{ marginBottom: 20 }}>
      <div className="row">
        <strong>Revenue &amp; net income (B)</strong>
      </div>
      {rows === null && <div className="empty">Loading chart...</div>}
      {rows !== null && !chart && <div className="empty">No fundamentals on file.</div>}
      {chart && <GroupedBarChart categories={chart.categories} series={chart.series} height={300} fmt={(v) => `${v.toFixed(2)}B`} />}
    </section>
  );
}

export default function MetricsTab({ apiKey, ticker }: TickerProps) {
  const [metrics, setMetrics] = useState<InstrumentMetric[] | null>(null);
  const [ratios, setRatios] = useState<FundamentalRatio | null | "none">(null);
  const [window, setWindow] = useState("1y");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ticker) return;
    setMetrics(null);
    setRatios(null);
    setError(null);
    api<InstrumentMetric[]>(`/instruments/${ticker}/metrics`, apiKey)
      .then(setMetrics)
      .catch((e) => setError(errMsg(e)));
    api<FundamentalRatio>(`/instruments/${ticker}/ratios`, apiKey)
      .then(setRatios)
      .catch(() => setRatios("none"));
  }, [apiKey, ticker]);

  if (!ticker) return <div className="empty">Select a ticker.</div>;
  if (error) return <div className="status err">Error: {error}</div>;

  const windows = [...new Set((metrics ?? []).map((m) => m.window))].sort();
  const m = metrics?.find((x) => x.window === window) ?? metrics?.[0] ?? null;

  const riskTiles: Tile[] = m
    ? [
        { label: "Sharpe", value: num2(m.sharpe), tone: "pos", raw: m.sharpe },
        { label: "Sortino", value: num2(m.sortino), tone: "pos", raw: m.sortino },
        { label: "Volatility", value: pctRatio(m.volatility) },
        { label: "Max drawdown", value: pctRatio(m.max_drawdown), tone: "loss" },
        { label: "VaR 95%", value: pctRatio(m.var_95), tone: "loss" },
        { label: "Total return", value: pctRatio(m.total_return), tone: "pos", raw: m.total_return },
        { label: "Beta S&P 500", value: num2(m.beta_sp500) },
        { label: `Alpha S&P (${m.alpha_label_sp500 ?? ""})`, value: pctRatio(m.alpha_sp500), tone: "pos", raw: m.alpha_sp500 },
        { label: "Beta TSX", value: num2(m.beta_tsx) },
        { label: `Alpha TSX (${m.alpha_label_tsx ?? ""})`, value: pctRatio(m.alpha_tsx), tone: "pos", raw: m.alpha_tsx },
      ]
    : [];

  const r = ratios && ratios !== "none" ? ratios : null;
  const ratioTiles: Tile[] = r
    ? [
        { label: "Net margin", value: pctRatio(r.net_margin), tone: "pos", raw: r.net_margin },
        { label: "Gross margin", value: pctRatio(r.gross_margin), tone: "pos", raw: r.gross_margin },
        { label: "Op. margin", value: pctRatio(r.operating_margin), tone: "pos", raw: r.operating_margin },
        { label: "ROE", value: pctRaw(r.roe), tone: "pos", raw: r.roe },
        { label: "ROA", value: pctRaw(r.roa), tone: "pos", raw: r.roa },
        { label: "ROIC", value: pctRaw(r.roic), tone: "pos", raw: r.roic },
        { label: "P/E", value: num2(r.pe) },
        { label: "P/B", value: num2(r.pb) },
        { label: "P/S", value: num2(r.ps) },
        { label: "EV/EBITDA", value: num2(r.ev_ebitda) },
        { label: "Debt/Equity", value: num2(r.debt_to_equity) },
        { label: "Revenue YoY", value: pctRatio(r.revenue_yoy), tone: "pos", raw: r.revenue_yoy },
        { label: "EPS TTM", value: num2(r.eps_ttm) },
        { label: "FCF yield", value: pctRatio(r.fcf_yield), tone: "pos", raw: r.fcf_yield },
      ]
    : [];

  return (
    <>
      {metrics !== null && metrics.length === 0 && (
        <div className="empty">No metrics computed yet (run the metrics pipeline).</div>
      )}

      {m && (
        <div className="row" style={{ alignItems: "center", gap: 12 }}>
          <div className="tabs" style={{ marginBottom: 0 }}>
            {windows.map((w) => (
              <button key={w} className={window === w ? "active" : ""} onClick={() => setWindow(w)}>
                {w}
              </button>
            ))}
          </div>
          <span className="muted" style={{ fontSize: 12 }}>
            as of {m.as_of} · window {m.window} · risk-free {m.rf_annual != null ? `${(m.rf_annual * 100).toFixed(2)}%` : dash}
          </span>
        </div>
      )}

      <TileGrid title="Risk & performance" tiles={riskTiles} />
      <TileGrid title="Fundamental ratios" tiles={ratioTiles} />
      {ratios === "none" && (
        <div className="muted" style={{ marginBottom: 16, fontSize: 12 }}>
          No fundamental ratios on file for this ticker yet.
        </div>
      )}

      <ChartPanel apiKey={apiKey} ticker={ticker} />
      <FundamentalsChartPanel apiKey={apiKey} ticker={ticker} />
    </>
  );
}
