// Shapes returned by the FastAPI backend (src/api/schemas.py). Kept in sync by
// hand -- these mirror the Pydantic response models the API serves.

export interface Instrument {
  id: number;
  ticker: string;
  name: string | null;
  exchange: string | null;
  currency: string;
  timezone: string;
  is_active: boolean;
  is_scheduled: boolean;
}

export interface Price {
  symbol: string;
  ts: string; // ISO date, e.g. "2026-01-02"
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  close_returns: number | null;
}

export interface Fundamental {
  ticker: string;
  concept: string;
  unit: string;
  period_end: string;
  fy: number | null;
  fp: string;
  form: string;
  val: number;
}

export interface InstrumentMetric {
  symbol: string;
  as_of: string;
  window: string;
  rf_annual: number | null;
  sharpe: number | null;
  sortino: number | null;
  max_drawdown: number | null;
  var_95: number | null;
  volatility: number | null;
  total_return: number | null;
  beta_sp500: number | null;
  alpha_sp500: number | null;
  alpha_label_sp500: string | null;
  beta_tsx: number | null;
  alpha_tsx: number | null;
  alpha_label_tsx: string | null;
}

export interface FundamentalRatio {
  ticker: string;
  as_of: string;
  gross_margin: number | null;
  operating_margin: number | null;
  net_margin: number | null;
  roe: number | null;
  roa: number | null;
  roic: number | null;
  net_debt: number | null;
  net_debt_ebitda: number | null;
  debt_to_equity: number | null;
  revenue_yoy: number | null;
  net_income_yoy: number | null;
  eps_ttm: number | null;
  pe: number | null;
  ps: number | null;
  pb: number | null;
  ev: number | null;
  ev_ebitda: number | null;
  ev_sales: number | null;
  fcf_yield: number | null;
}

export interface MacroPoint {
  series: string;
  ts: string;
  value: number | null;
}

export interface MacroCatalogEntry {
  code: string;
  label: string;
}

// Grouped FRED/FX catalog, e.g. { US: [...], Canada: [...], FX: [...] }.
export type MacroCatalog = Record<string, MacroCatalogEntry[]>;

export interface ApiKeyInfo {
  id: number;
  label: string;
  prefix: string;
  scopes: string; // comma-separated, e.g. "read" or "read,write"
  is_active: boolean;
  created_at: string | null;
  last_used_at: string | null;
}

// The create response additionally carries the plaintext token, shown once.
export interface ApiKeyCreated extends ApiKeyInfo {
  key: string;
}

export interface NavPage {
  key: string;
  label: string;
}
