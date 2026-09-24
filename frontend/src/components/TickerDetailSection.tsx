import { useEffect, useState } from "react";
import PricesTab from "./PricesTab";
import FundamentalsTab from "./FundamentalsTab";
import MetricsTab from "./MetricsTab";
import type { Instrument } from "../types";

interface TickerDetailSectionProps {
  apiKey: string;
  instruments: Instrument[];
}

const TABS = [
  { key: "prices", label: "Prices" },
  { key: "fundamentals", label: "Fundamentals" },
  { key: "metrics", label: "Metrics & charts" },
];

export default function TickerDetailSection({ apiKey, instruments }: TickerDetailSectionProps) {
  const [ticker, setTicker] = useState("");
  const [tab, setTab] = useState("prices");

  useEffect(() => {
    if (ticker && !instruments.some((i) => i.ticker === ticker)) setTicker("");
  }, [instruments, ticker]);

  return (
    <section>
      <h2>Ticker detail</h2>
      <div className="row">
        <select value={ticker} onChange={(e) => setTicker(e.target.value)}>
          <option value="">Select a ticker...</option>
          {instruments.map((i) => (
            <option key={i.ticker} value={i.ticker}>
              {i.ticker}
            </option>
          ))}
        </select>
      </div>
      <div className="tabs">
        {TABS.map((t) => (
          <button key={t.key} className={tab === t.key ? "active" : ""} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === "prices" && <PricesTab apiKey={apiKey} ticker={ticker} />}
      {tab === "fundamentals" && <FundamentalsTab apiKey={apiKey} ticker={ticker} />}
      {tab === "metrics" && <MetricsTab apiKey={apiKey} ticker={ticker} />}
    </section>
  );
}
