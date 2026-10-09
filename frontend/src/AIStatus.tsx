import { useEffect, useState } from "react";
import { request } from "./api";

export default function AIStatus() {
  const [status, setStatus] = useState("unavailable");
  useEffect(() => {
    let active = true;
    const refresh = () =>
      request<{ status: string }>("/ai/status")
        .then((data) => {
          if (active) {
            setStatus(data.status);
          }
        })
        .catch(() => {
          if (active) setStatus("unavailable");
        });
    void refresh();
    const timer = window.setInterval(refresh, 10000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);
  const connected = status === "connected" || status === "unverified";
  return (
    <span
      className={`ai-status ${connected ? "connected" : "disconnected"}`}
      aria-live="polite"
    >
      <i aria-hidden="true" />
      {connected ? "AI Connected" : "AI Disconnected"}
    </span>
  );
}
