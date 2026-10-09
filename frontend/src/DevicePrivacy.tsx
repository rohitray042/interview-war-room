import { useEffect, useRef, useState } from "react";
import { Download, Trash2, Upload } from "lucide-react";
import { storageMode } from "./api";
import {
  clearWorkspace,
  exportWorkspace,
  importWorkspace,
  watchWorkspaceReset,
} from "./deviceStorage";

export default function DevicePrivacy({
  controls = false,
}: {
  controls?: boolean;
}) {
  const [mode, setMode] = useState<string>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  useEffect(() => {
    void storageMode()
      .then(setMode)
      .catch(() => {});
  }, []);
  useEffect(
    () => (mode === "browser" ? watchWorkspaceReset() : undefined),
    [mode],
  );
  if (mode !== "browser") return null;

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Could not update browser data.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="device-privacy" aria-label="Device privacy">
      <p>
        <strong>Saved in this browser.</strong> Your resume, JD and interview
        history stay in this browser's storage. Your workspace is sent to the
        backend for temporary processing in memory, with no application database
        saved there. Selected context goes to the AI provider only with your
        consent.
      </p>
      {controls && (
        <>
          <p>
            Other devices and browser profiles start empty. Anyone using this
            same browser profile can access this workspace. Clearing site data
            or using private browsing can remove your history. Backups contain
            your personal data as readable text.
          </p>
          <div className="device-actions">
            <button
              type="button"
              disabled={busy}
              onClick={() => void run(exportWorkspace)}
            >
              <Download size={16} /> Export backup
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => file.current?.click()}
            >
              <Upload size={16} /> Restore backup
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                if (
                  confirm(
                    "Delete this browser's resume, JD, profile and interview history? Export a backup first to keep a copy.",
                  )
                )
                  void run(clearWorkspace);
              }}
            >
              <Trash2 size={16} /> Delete device data
            </button>
            <input
              ref={file}
              type="file"
              accept="application/json,.json"
              hidden
              onChange={(event) => {
                const selected = event.target.files?.[0];
                event.target.value = "";
                if (
                  selected &&
                  confirm(
                    "Replace this browser's workspace with the selected backup?",
                  )
                )
                  void run(() => importWorkspace(selected));
              }}
            />
          </div>
          {error && <p role="alert">{error}</p>}
        </>
      )}
    </section>
  );
}
