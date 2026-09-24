import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type SetStateAction,
} from "react";
import { api, apiWithTotal, errMsg } from "../api";
import {
  KEY_METRICS,
  KEY_METRIC_CONCEPTS,
  prettyConcept,
  fmtCompact,
  type MetricKind,
} from "../fundamentalsMeta";
import type { Fundamental } from "../types";

type Order = "asc" | "desc";

interface Column {
  key: string;
  label: string;
  num?: boolean;
}

const EXPLORER_COLUMNS: Column[] = [
  { key: "concept", label: "Concept" },
  { key: "period_end", label: "Period end" },
  { key: "fy", label: "FY", num: true },
  { key: "fp", label: "FP" },
  { key: "form", label: "Form" },
  { key: "val", label: "Value", num: true },
];

// Truncate the long concept column with an ellipsis (full name on hover).
const CONCEPT_CELL: CSSProperties = {
  maxWidth: 240,
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const PAGE_SIZES = [25, 50, 100, 250];

// Keeps the metric-name column pinned while the period columns scroll sideways.
const STICKY_COL: CSSProperties = { position: "sticky", left: 0, background: "var(--panel)", zIndex: 1 };

interface TickerProps {
  apiKey: string;
  ticker: string;
}

interface MetricRow {
  label: string;
  kind: MetricKind;
  concept: string | undefined;
  byPeriod: Record<string, number>;
}

// ---- Curated "Key financials" -------------------------------------------------
function KeyFinancials({ apiKey, ticker }: TickerProps) {
  // Period, not SEC form: works uniformly for US (10-Q/10-K) and CAD (YF-Q/YF-A).
  const [period, setPeriod] = useState<"quarterly" | "annual">("quarterly");
  const [rows, setRows] = useState<Fundamental[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ticker) return;
    setRows(null);
    setError(null);
    const qs = new URLSearchParams({
      concepts: KEY_METRIC_CONCEPTS.join(","),
      period,
      limit: "3000",
      sort_by: "period_end",
      order: "desc",
    });
    api<Fundamental[]>(`/fundamentals/${ticker}?${qs}`, apiKey)
      .then(setRows)
      .catch((e) => setError(errMsg(e)));
  }, [ticker, apiKey, period]);

  const { periods, metricRows } = useMemo<{ periods: string[]; metricRows: MetricRow[] }>(() => {
    if (!rows || rows.length === 0) return { periods: [], metricRows: [] };
    // Newest first, capped; the table scrolls horizontally to older periods.
    const periods = [...new Set(rows.map((r) => r.period_end))].sort().reverse().slice(0, 40);

    const metricRows = KEY_METRICS.map((m) => {
      const concept = m.concepts.find((c) => rows.some((r) => r.concept === c));
      const byPeriod: Record<string, number> = {};
      if (concept) {
        for (const r of rows) {
          if (r.concept === concept) byPeriod[r.period_end] = r.val;
        }
      }
      return { label: m.label, kind: m.kind, concept, byPeriod };
    }).filter((m) => m.concept);

    return { periods, metricRows };
  }, [rows]);

  return (
    <section style={{ marginBottom: 20 }}>
      <div className="row">
        <strong>Key financials</strong>
        <div className="tabs" style={{ marginBottom: 0, marginLeft: "auto" }}>
          {(["quarterly", "annual"] as const).map((p) => (
            <button key={p} className={period === p ? "active" : ""} onClick={() => setPeriod(p)}>
              {p === "quarterly" ? "Quarterly" : "Annual"}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="empty">Error: {error}</div>}
      {!error && rows === null && <div className="empty">Loading...</div>}
      {!error && rows !== null && metricRows.length === 0 && (
        <div className="empty">No {period} key financials on file.</div>
      )}
      {!error && metricRows.length > 0 && (
        <>
          {periods.length > 5 && (
            <div className="muted" style={{ marginBottom: 6, fontSize: 12 }}>
              ↔ scroll sideways to see older periods
            </div>
          )}
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th style={STICKY_COL}>Metric</th>
                  {periods.map((p) => (
                    <th key={p} style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      {p}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {metricRows.map((m) => (
                  <tr key={m.label}>
                    <td title={m.concept} style={STICKY_COL}>
                      {m.label}
                    </td>
                    {periods.map((p) => (
                      <td key={p} style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                        {fmtCompact(m.byPeriod[p], m.kind)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

// Multi-concept picker (search + checkboxes). Empty selection = all concepts.
interface ConceptPickerProps {
  concepts: string[];
  selected: string[];
  setSelected: (updater: SetStateAction<string[]>) => void;
}

function ConceptPicker({ concepts, selected, setSelected }: ConceptPickerProps) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const boxRef = useRef<HTMLDivElement>(null);

  // Close when clicking outside the picker.
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const base = needle
      ? concepts.filter(
          (c) => c.toLowerCase().includes(needle) || prettyConcept(c).toLowerCase().includes(needle),
        )
      : concepts;
    return base.slice(0, 300); // cap rendered rows for performance
  }, [concepts, q]);

  function toggle(c: string) {
    setSelected((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]));
  }

  return (
    <div ref={boxRef} style={{ position: "relative" }}>
      <button onClick={() => setOpen((o) => !o)}>
        Choose concepts{selected.length ? ` (${selected.length})` : ""} ▾
      </button>
      {open && (
        <div
          style={{
            position: "absolute",
            zIndex: 20,
            top: "calc(100% + 4px)",
            left: 0,
            width: 380,
            background: "var(--panel)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: 8,
            boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
          }}
        >
          <input
            type="text"
            autoFocus
            placeholder="search concept..."
            value={q}
            onChange={(e) => setQ(e.target.value)}
            style={{ width: "100%", marginBottom: 6 }}
          />
          <div style={{ maxHeight: 280, overflowY: "auto" }}>
            {filtered.length === 0 && <div className="empty" style={{ padding: 6 }}>No match.</div>}
            {filtered.map((c) => (
              <label
                key={c}
                style={{ display: "flex", alignItems: "center", gap: 8, padding: "3px 4px", cursor: "pointer" }}
                title={c}
              >
                <input type="checkbox" checked={selected.includes(c)} onChange={() => toggle(c)} />
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {prettyConcept(c)}
                </span>
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---- Full explorer ------------------------------------------------------------
function Explorer({ apiKey, ticker }: TickerProps) {
  const [concepts, setConcepts] = useState<string[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [period, setPeriod] = useState("");
  const [sortBy, setSortBy] = useState("period_end");
  const [order, setOrder] = useState<Order>("desc");
  const [pageSize, setPageSize] = useState(50);
  const [page, setPage] = useState(0);
  const [rows, setRows] = useState<Fundamental[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const offset = page * pageSize;

  useEffect(() => {
    if (!ticker) return;
    setSelected([]);
    api<string[]>(`/fundamentals/${ticker}/concepts`, apiKey)
      .then(setConcepts)
      .catch(() => setConcepts([]));
  }, [ticker, apiKey]);

  // On selection change: reset to page 1 and group rows by concept.
  function updateSelected(updater: SetStateAction<string[]>) {
    setSelected((prev) => {
      const next = typeof updater === "function" ? updater(prev) : updater;
      if (next.length > 0) {
        setSortBy("concept");
        setOrder("asc");
      } else {
        setSortBy("period_end");
        setOrder("desc");
      }
      return next;
    });
    setPage(0);
  }

  useEffect(() => {
    if (!ticker) return;
    setRows(null);
    setError(null);
    const qs = new URLSearchParams({
      limit: String(pageSize),
      offset: String(offset),
      sort_by: sortBy,
      order,
    });
    if (selected.length) qs.set("concepts", selected.join(","));
    if (period) qs.set("period", period);
    apiWithTotal<Fundamental[]>(`/fundamentals/${ticker}?${qs}`, apiKey)
      .then(({ data, total }) => {
        setRows(data);
        setTotal(total);
      })
      .catch((e) => setError(errMsg(e)));
  }, [ticker, apiKey, selected, period, sortBy, order, pageSize, offset]);

  function changeSort(key: string) {
    if (key === sortBy) setOrder((o) => (o === "asc" ? "desc" : "asc"));
    else {
      setSortBy(key);
      setOrder("desc");
    }
    setPage(0);
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <section>
      <div className="row">
        <strong>Explore concepts</strong>
      </div>
      <div className="row">
        <ConceptPicker concepts={concepts} selected={selected} setSelected={updateSelected} />
        <select
          value={period}
          onChange={(e) => {
            setPeriod(e.target.value);
            setPage(0);
          }}
        >
          <option value="">All periods</option>
          <option value="annual">Annual</option>
          <option value="quarterly">Quarterly</option>
        </select>
        {(selected.length > 0 || period) && (
          <button
            onClick={() => {
              updateSelected([]);
              setPeriod("");
            }}
          >
            Clear
          </button>
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

      {selected.length > 0 && (
        <div className="row" style={{ gap: 6 }}>
          {selected.map((c) => (
            <span
              key={c}
              className="pill on"
              style={{ cursor: "pointer" }}
              title={c}
              onClick={() => updateSelected((prev) => prev.filter((x) => x !== c))}
            >
              {prettyConcept(c)} ✕
            </span>
          ))}
        </div>
      )}

      {error && <div className="status err">Error: {error}</div>}
      {!error && rows === null && <div className="empty">Loading...</div>}

      {!error && rows !== null && (
        <>
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  {EXPLORER_COLUMNS.map((c) => {
                    const active = c.key === sortBy;
                    return (
                      <th
                        key={c.key}
                        onClick={() => changeSort(c.key)}
                        style={{
                          cursor: "pointer",
                          userSelect: "none",
                          textAlign: c.num ? "right" : "left",
                          ...(c.key === "concept" ? CONCEPT_CELL : {}),
                        }}
                        title="Click to sort"
                      >
                        {c.label}
                        {active ? (order === "asc" ? " ▲" : " ▼") : ""}
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={i}>
                    <td title={row.concept} style={CONCEPT_CELL}>
                      {prettyConcept(row.concept)}
                    </td>
                    <td>{row.period_end}</td>
                    <td style={{ textAlign: "right" }}>{row.fy ?? ""}</td>
                    <td>{row.fp}</td>
                    <td>{row.form}</td>
                    <td style={{ textAlign: "right" }}>
                      {fmtCompact(row.val, row.unit === "USD/shares" ? "perShare" : "money")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {rows.length === 0 ? (
            <div className="empty">No facts match this filter.</div>
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

export default function FundamentalsTab({ apiKey, ticker }: TickerProps) {
  if (!ticker) return <div className="empty">Select a ticker.</div>;
  return (
    <>
      <KeyFinancials apiKey={apiKey} ticker={ticker} />
      <Explorer apiKey={apiKey} ticker={ticker} />
    </>
  );
}
