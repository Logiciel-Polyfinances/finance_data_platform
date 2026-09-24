import { useCallback, useEffect, useState } from "react";
import { api, errMsg } from "./api";
import type { Instrument, NavPage } from "./types";
import Header from "./components/Header";
import InstrumentsSection from "./components/InstrumentsSection";
import TickerDetailSection from "./components/TickerDetailSection";
import MacroSection from "./components/MacroSection";
import ApiKeysSection from "./components/ApiKeysSection";

const PAGES: NavPage[] = [
  { key: "instruments", label: "Instruments" },
  { key: "ticker", label: "Ticker detail" },
  { key: "macro", label: "Macro / FX" },
  { key: "keys", label: "API keys" },
];

export default function App() {
  const [apiKey, setApiKey] = useState<string>(
    () => localStorage.getItem("apiKey") || import.meta.env.VITE_API_KEY || "",
  );
  const [page, setPage] = useState<string>(() => localStorage.getItem("page") || "instruments");
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    localStorage.setItem("apiKey", apiKey);
  }, [apiKey]);

  useEffect(() => {
    localStorage.setItem("page", page);
  }, [page]);

  const reload = useCallback(async () => {
    setRefreshing(true);
    try {
      const body = await api<Instrument[]>("/instruments", apiKey);
      setInstruments(body);
      setLoadError(null);
    } catch (e) {
      setLoadError(`Could not reach the API: ${errMsg(e)}`);
    } finally {
      setRefreshing(false);
    }
  }, [apiKey]);

  useEffect(() => {
    reload();
  }, [reload]);

  return (
    <>
      <Header
        apiKey={apiKey}
        setApiKey={setApiKey}
        onRefresh={reload}
        refreshing={refreshing}
        page={page}
        setPage={setPage}
        pages={PAGES}
      />
      <main>
        {loadError && <div className="status err">{loadError}</div>}
        {page === "instruments" && (
          <InstrumentsSection apiKey={apiKey} instruments={instruments} reload={reload} />
        )}
        {page === "ticker" && <TickerDetailSection apiKey={apiKey} instruments={instruments} />}
        {page === "macro" && <MacroSection apiKey={apiKey} />}
        {page === "keys" && <ApiKeysSection apiKey={apiKey} />}
      </main>
    </>
  );
}
