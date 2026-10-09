import { useEffect, useState } from "react";
import { request } from "./api";

export default function AIStatus() {
  const [status, setStatus] = useState("unavailable");
  const [metadata, setMetadata] = useState("");
  useEffect(() => {
    let active = true;
    const refresh = () =>
      request<{ status: string; provider?: string; model?: string }>(
        "/ai/status",
      )
        .then((data) => {
          if (active) {
            setStatus(data.status);
            setMetadata(
              [data.provider, data.model].filter(Boolean).join(" · "),
            );
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
  const labels: Record<string, string> = {
    connected: "AI Connected",
    disabled: "AI Disabled",
    mock: "AI Mock",
    unverified: "AI Unverified",
    unavailable: "AI Unavailable",
  };
  return (
    <span
      title="Status reflects the last provider response. Configure AI in backend environment variables."
      style={{ fontSize: 12 }}
    >
      {labels[status] || labels.unavailable}
      {metadata && <small style={{ display: "block" }}>{metadata}</small>}
    </span>
  );
}
