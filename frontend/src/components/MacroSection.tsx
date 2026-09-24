import { useEffect, useMemo, useState } from "react";
import { api, apiWithTotal, errMsg, fmtNum } from "../api";
import type { MacroCatalog, MacroPoint } from "../types";
import TimeSeriesChart, { type TsPoint } from "./TimeSeriesChart";

const PAGE_SIZES = [25, 50, 100, 250];

const ACCENT = "#4f8cff"; // app accent, reads on the dark surface
const MACRO_RANGES: [string, number][] = [
  ["1Y", 365],
  ["5Y", 1825],
  ["10Y", 3650],
  ["Max", 1e9],
];

const macroFmt = (v: number) =>
  v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// Interactive line for one FRED/FX series (US or CAD alike).
function MacroChart({ apiKey, series, label }: { apiKey: string; series: string; label: string }) {
  const [points, setPoints] = useState<MacroPoint[] | null>(null);
  const [range, setRange] = useState(1825);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!series) return;
    setPoints(null);
    setError(null);
    api<MacroPoint[]>(`/macro/${series}?limit=5000&order=asc`, apiKey)
      .then(setPoints)
      .catch((e) => setError(errMsg(e)));
  }, [series, apiKey]);

  const data = useMemo<TsPoint[]>(() => {
    if (!points) return [];
    const clean = points.filter((p) => p.value != null) as (MacroPoint & { value: number })[];
    const cutoff = range >= 1e9 ? "" : new Date(Date.now() - range * 864e5).toISOString().slice(0, 10);
    const sliced = cutoff ? clean.filter((p) => p.ts >= cutoff) : clean;
    return sliced.map((p) => ({ t: p.ts, v: p.value }));
  }, [points, range]);

  return (
    <section style={{ marginBottom: 16 }}>
      <div className="row">
        <strong>{label}</strong>
        <div className="tabs" style={{ marginBottom: 0, marginLeft: "auto" }}>
          {MACRO_RANGES.map(([lbl, days]) => (
            <button key={lbl} className={range === days ? "active" : ""} onClick={() => setRange(days)}>
              {lbl}
            </button>
          ))}
        </div>
      </div>
      {error && <div className="empty">No chart: {error}</div>}
      {!error && points === null && <div className="empty">Loading chart...</div>}
      {!error && points !== null && data.length > 1 && (
        <TimeSeriesChart data={data} color={ACCENT} height={260} fmt={macroFmt} />
      )}
      {!error && points !== null && data.length <= 1 && (
        <div className="empty">Not enough observations in range.</div>
      )}
    </section>
  );
}

interface MacroSectionProps {
  apiKey: string;
}

export default function MacroSection({ apiKey }: MacroSectionProps) {
  const [catalog, setCatalog] = useState<MacroCatalog | null>(null);
  const [group, setGroup] = useState("US");
  const [series, setSeries] = useState("");
  const [rows, setRows] = useState<MacroPoint[] | null>(null);
  const [total, setTotal] = useState(0);
  const [pageSize, setPageSize] = useState(50);
  const [page, setPage] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const offset = page * pageSize;

  // Load the grouped catalog once.
  useEffect(() => {
    api<MacroCatalog>("/macro/catalog", apiKey)
      .then((cat) => {
        setCatalog(cat);
        const groups = Object.keys(cat);
        const g = groups.includes("US") ? "US" : groups[0];
        setGroup(g);
        setSeries(cat[g]?.[0]?.code || "");
      })
      .catch((e) => setError(errMsg(e)));
  }, [apiKey]);

  // Fetch the selected series' observations (newest first, paginated server-side).
  useEffect(() => {
    if (!series) return;
    setRows(null);
    setError(null);
    const qs = new URLSearchParams({
      limit: String(pageSize),
      offset: String(offset),
      order: "desc",
    });
    apiWithTotal<MacroPoint[]>(`/macro/${series}?${qs}`, apiKey)
      .then(({ data, total }) => {
        setRows(data);
        setTotal(total);
      })
      .catch((e) => setError(errMsg(e)));
  }, [series, apiKey, pageSize, offset]);

  function pickGroup(g: string) {
    setGroup(g);
    setSeries(catalog?.[g]?.[0]?.code || "");
    setPage(0);
  }

  const options = catalog?.[group] || [];
  const selectedLabel = options.find((o) => o.code === series)?.label || series;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <section>
      <h2>
        Macro / FX <span className="muted">FRED series — US &amp; Canada</span>
      </h2>

      {catalog && (
        <div className="tabs">
          {Object.keys(catalog).map((g) => (
            <button key={g} className={group === g ? "active" : ""} onClick={() => pickGroup(g)}>
              {g}
            </button>
          ))}
        </div>
      )}

      <div className="row">
        <select
          value={series}
          onChange={(e) => {
            setSeries(e.target.value);
            setPage(0);
          }}
        >
          {options.map((s) => (
            <option key={s.code} value={s.code}>
              {s.label}
            </option>
          ))}
        </select>
        {series && (
          <span className="muted">
            series code: <code>{series}</code>
          </span>
        )}
        <div className="field" style={{ marginLeft: "auto" }}>
          <label>Rows</label>
          <select
            value={pageSize}
            onChange={(e) => {
              setPageSize(Number(e.target.value));
              setPage(0);
            }}
          >
            {PAGE_SIZES.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>
      </div>

      {series && <MacroChart apiKey={apiKey} series={series} label={selectedLabel} />}

      {error && <div className="empty">Error: {error}</div>}
      {!error && rows === null && <div className="empty">Loading...</div>}
      {!error && rows !== null && (
        <>
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th style={{ textAlign: "right" }}>Value</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.ts}>
                    <td>{row.ts}</td>
                    <td style={{ textAlign: "right" }}>{fmtNum(row.value, 3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {rows.length === 0 ? (
            <div className="empty">No data for this series yet — run the FRED macro DAG for it.</div>
          ) : (
            <div className="row" style={{ marginTop: 12, marginBottom: 0 }}>
              <span className="muted">
                {offset + 1}-{offset + rows.length} of {total}
              </span>
              <div className="field" style={{ marginLeft: "auto", gap: 8 }}>
                <button className="pagebtn" disabled={page === 0} onClick={() => setPage(0)}>
                  « First
                </button>
                <button className="pagebtn" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                  ‹ Prev
                </button>
                <span className="muted">
                  Page {page + 1} / {totalPages}
                </span>
                <button
                  className="pagebtn"
                  disabled={page + 1 >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next ›
                </button>
                <button
                  className="pagebtn"
                  disabled={page + 1 >= totalPages}
                  onClick={() => setPage(totalPages - 1)}
                >
                  Last »
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
