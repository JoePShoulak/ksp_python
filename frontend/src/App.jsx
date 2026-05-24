import { useEffect, useState } from "react";
import "./App.css";

import { ACTIONS } from "./data/actions";
import { getStatus, runKspAction } from "./api/kspApi";

import StatusPanel from "./components/StatusPanel";
import ActionsPanel from "./components/ActionsPanel";
import ResponsePanel from "./components/ResponsePanel";
import LogPanel from "./components/LogPanel";
import TelemetryPanel from "./components/TelemetryPanel";
import VisDatPanel from "./components/VisDatPanel";

function App() {
  const [apiStatus, setApiStatus] = useState("Unknown");
  const [isLoading, setIsLoading] = useState(false);
  const [lastResponse, setLastResponse] = useState(null);
  const [log, setLog] = useState([]);
  const [telemetryEnabled, setTelemetryEnabled] = useState(false);
  const [telemetry, setTelemetry] = useState(null);

  function addLog(message) {
    const timestamp = new Date().toLocaleTimeString();

    setLog(previousLog => [
      {
        id: crypto.randomUUID(),
        timestamp,
        message,
      },
      ...previousLog,
    ]);
  }

  async function checkStatus() {
    try {
      const data = await getStatus();

      setApiStatus(data.message);
      addLog("Status check succeeded");
    } catch (error) {
      setApiStatus("Flask API is not reachable");
      addLog(`Status check failed: ${error.message}`);
    }
  }

  async function handleRunAction(actionId) {
    setIsLoading(true);
    setLastResponse(null);

    try {
      addLog(`Sending action: ${actionId}`);

      const data = await runKspAction(actionId);

      setLastResponse(data);
      addLog(data.message);
    } catch (error) {
      const errorResponse = {
        ok: false,
        error: error.message,
      };

      setLastResponse(errorResponse);
      addLog(`Error: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  }

  function toggleTelemetry() {
    setTelemetryEnabled(previousValue => {
      const nextValue = !previousValue;

      addLog(
        nextValue ? "Telemetry polling enabled" : "Telemetry polling disabled",
      );

      return nextValue;
    });
  }

  useEffect(() => {
    const controller = new AbortController();

    getStatus({
      signal: controller.signal,
    })
      .then(data => {
        setApiStatus(data.message);

        const timestamp = new Date().toLocaleTimeString();

        setLog(previousLog => [
          {
            id: crypto.randomUUID(),
            timestamp,
            message: "Status check succeeded",
          },
          ...previousLog,
        ]);
      })
      .catch(error => {
        if (error.name === "AbortError") {
          return;
        }

        setApiStatus("Flask API is not reachable");

        const timestamp = new Date().toLocaleTimeString();

        setLog(previousLog => [
          {
            id: crypto.randomUUID(),
            timestamp,
            message: `Status check failed: ${error.message}`,
          },
          ...previousLog,
        ]);
      });

    return () => {
      controller.abort();
    };
  }, []);

  return (
    <main className="app">
      <h1>KSP Control Panel</h1>
      <StatusPanel
        apiStatus={apiStatus}
        isLoading={isLoading}
        onRefresh={checkStatus}
      />
      <TelemetryPanel
        enabled={telemetryEnabled}
        onToggle={toggleTelemetry}
        telemetry={telemetry}
        setTelemetry={setTelemetry}
      />
      <VisDatPanel telemetry={telemetry} />
      <ActionsPanel
        actions={ACTIONS}
        isLoading={isLoading}
        onRunAction={handleRunAction}
      />
      <ResponsePanel lastResponse={lastResponse} />
      <LogPanel log={log} />
    </main>
  );
}

export default App;
