import { useEffect, useRef, useState } from "react";
import { Download, Trash2, Upload } from "lucide-react";
import { storageMode } from "./api";
import { accountSession } from "./cloudAccount";
import {
  clearWorkspace,
  exportWorkspace,
  importWorkspace,
  watchWorkspaceReset,
} from "./deviceStorage";

export default function DevicePrivacy({
  controls = false,
  onAccount,
}: {
  controls?: boolean;
  onAccount?: () => void;
}) {
  const [mode, setMode] = useState<string>();
  const [cloud, setCloud] = useState(false);
  const [expired, setExpired] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  useEffect(() => {
    void accountSession()
      .then((account) => {
        setCloud(!!account.user);
        setExpired(!!account.expired);
      })
      .catch(() => {});
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
        {expired ? (
          <>
            <strong>Cloud session expired.</strong> Log in again or choose
            Return to guest workspace in account settings.
          </>
        ) : cloud ? (
          <>
            <strong>Saved to your private account.</strong> Your resume, JD and
            interview history are stored in cloud storage for access from your
            other devices. Selected context goes to the AI provider with your
            consent.
          </>
        ) : (
          <>
            <strong>Saved in this browser.</strong> Your resume, JD and
            interview history stay in this browser's storage. Your workspace is
            sent to the backend for temporary processing in memory, with no
            application database saved there. Selected context goes to the AI
            provider only with your consent.
          </>
        )}
      </p>
      {!controls && onAccount && (
        <button type="button" className="text-action" onClick={onAccount}>
          {cloud ? "Manage account" : "Log in / Sign up to save across devices"}
        </button>
      )}
      {controls && (
        <>
          <p>
            {cloud ? (
              "Log out on shared devices. Cloud backups contain your personal data as readable text. Guest browser data is kept separate."
            ) : (
              <>
                Other devices and browser profiles start empty. Anyone using
                this same browser profile can access this workspace. Clearing
                site data or using private browsing can remove your history.
                Backups contain your personal data as readable text.
              </>
            )}
          </p>
          <div className="device-actions">
            <button
              type="button"
              disabled={busy || expired}
              onClick={() => void run(exportWorkspace)}
            >
              <Download size={16} /> Export backup
            </button>
            <button
              type="button"
              disabled={busy || cloud || expired}
              onClick={() => file.current?.click()}
            >
              <Upload size={16} /> Restore backup
            </button>
            <button
              type="button"
              disabled={busy || cloud || expired}
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
