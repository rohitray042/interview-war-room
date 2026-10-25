import { useEffect, useState } from "react";
import { LogIn, LogOut, CloudUpload, UserPlus, Trash2 } from "lucide-react";
import {
  accountSession,
  accountChanged,
  cloudCall,
  watchAccount,
  type AccountSession,
} from "./cloudAccount";
import { saveGuestToAccount } from "./deviceStorage";

export default function AccountPanel() {
  const [account, setAccount] = useState<AccountSession>();
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState("");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => {
    accountSession()
      .then(setAccount)
      .catch((e) => setMessage(e.message));
    return watchAccount();
  }, []);
  async function run(work: () => Promise<void>) {
    setBusy(true);
    setMessage("");
    try {
      await work();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Account action failed.");
    } finally {
      setBusy(false);
    }
  }
  async function submit() {
    if (mode === "signup" && !consent)
      throw new Error("Please confirm cloud storage consent.");
    if (mode === "recover") {
      const result = await cloudCall<{ message: string }>("/recover", {
        email,
      });
      setMessage(result.message);
      setMode("reset");
      return;
    }
    if (mode === "verify" || mode === "reset") {
      await cloudCall("/verify", {
        email,
        token,
        type: mode === "reset" ? "recovery" : "signup",
        ...(mode === "reset" ? { password } : {}),
      });
      accountChanged();
      return;
    }
    const result = await cloudCall<{ message?: string }>("/" + mode, {
      email,
      password,
    });
    setPassword("");
    if (mode === "signup") {
      setMessage(result.message || "Check your email.");
      setMode("verify");
    } else accountChanged();
  }
  return (
    <section className="account-panel" aria-label="Account and cloud saving">
      <h2>
        {account?.user ? "Your cloud workspace" : "Save your progress anywhere"}
      </h2>
      {account?.user ? (
        <>
          <p>
            Signed in as {account.user.email}. Submitted work is saved to your
            private account and available on your other devices. Guest data
            stays separate in this browser.
          </p>
          <div className="device-actions">
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  if (
                    !confirm(
                      "Upload this browser's guest resume, JD and history into your empty cloud account? A guest copy remains on this device.",
                    )
                  )
                    return;
                  await saveGuestToAccount();
                  accountChanged();
                })
              }
            >
              <CloudUpload size={16} /> Import guest progress
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  await cloudCall("/logout", {});
                  accountChanged();
                })
              }
            >
              <LogOut size={16} /> Log out
            </button>
          </div>
          <details>
            <summary>Delete account and cloud data</summary>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void run(async () => {
                  if (
                    !confirm(
                      "Permanently delete your account and all cloud resumes and interview history? Export a backup first. This cannot be undone.",
                    )
                  )
                    return;
                  await cloudCall(
                    "/delete-account",
                    { email: account.user!.email, password },
                    account.user!.id,
                  );
                  accountChanged();
                });
              }}
            >
              <label>
                Confirm password
                <input
                  type="password"
                  autoComplete="current-password"
                  minLength={8}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </label>
              <button disabled={busy}>
                <Trash2 size={16} /> Delete account
              </button>
            </form>
          </details>
        </>
      ) : account?.enabled ? (
        <>
          <p>
            Guest mode needs no account. Sign up to store your resume, JD and
            interview history securely in cloud storage for access from another
            device. Existing guest work is uploaded only when you choose Import
            guest progress after login.
          </p>
          <div className="device-actions">
            {[
              ["login", "Log in"],
              ["signup", "Sign up"],
              ["recover", "Forgot password"],
              ["verify", "Verify email"],
            ].map(([key, label]) => (
              <button
                type="button"
                key={key}
                disabled={busy}
                aria-pressed={mode === key}
                onClick={() => {
                  setMode(key);
                  setMessage("");
                  setPassword("");
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void run(submit);
            }}
          >
            <label>
              Email
              <input
                type="email"
                autoComplete="email"
                maxLength={254}
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
            {["login", "signup", "reset"].includes(mode) && (
              <label>
                {mode === "reset" ? "New password" : "Password"}
                <input
                  type="password"
                  minLength={8}
                  maxLength={128}
                  required
                  autoComplete={
                    mode === "login" ? "current-password" : "new-password"
                  }
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </label>
            )}
            {["verify", "reset"].includes(mode) && (
              <label>
                Email code
                <input
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="[0-9]{6,10}"
                  required
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                />
              </label>
            )}
            {mode === "signup" && (
              <label className="account-consent">
                <input
                  type="checkbox"
                  required
                  checked={consent}
                  onChange={(e) => setConsent(e.target.checked)}
                />{" "}
                I agree to save account work in cloud storage. AI processing
                still requires separate consent. I can export or delete my data.
              </label>
            )}
            <button className="primary" disabled={busy}>
              {mode === "signup" ? <UserPlus size={16} /> : <LogIn size={16} />}
              {busy
                ? "Please wait..."
                : {
                    login: "Log in",
                    signup: "Create account",
                    recover: "Send recovery code",
                    verify: "Verify email",
                    reset: "Reset password",
                  }[mode]}
            </button>
          </form>
        </>
      ) : (
        <p>
          {account
            ? "Cloud accounts are not configured yet. You can continue using guest mode."
            : "Checking account service..."}
        </p>
      )}
      {account?.expired && (
        <p>
          Your session expired. Log in again to resume your cloud workspace.
        </p>
      )}
      {account?.expired && (
        <button
          type="button"
          disabled={busy}
          onClick={() =>
            void run(async () => {
              await cloudCall("/logout", {});
              accountChanged();
            })
          }
        >
          Return to guest workspace
        </button>
      )}
      {message && <p role="status">{message}</p>}
    </section>
  );
}
