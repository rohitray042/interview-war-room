import { accountSession, cloudCall } from "./cloudAccount";

export interface WorkspaceSnapshot {
  version: 1;
  schema_revision: "0005";
  tables: Record<string, Record<string, unknown>[]>;
}

interface StoredWorkspace {
  workspace: WorkspaceSnapshot;
}

const DB_NAME = "interview-war-room-device";
const STORE = "workspace";
const LOCK = "interview-war-room-workspace";
const MAX_BACKUP = 12 * 1024 * 1024;
let cloudRevision: number | undefined;

async function database(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const opened = indexedDB.open(DB_NAME, 1);
    opened.onupgradeneeded = () => opened.result.createObjectStore(STORE);
    opened.onsuccess = () => resolve(opened.result);
    opened.onerror = () =>
      reject(
        new Error(
          "Browser storage is unavailable. Enable site storage to continue.",
        ),
      );
    opened.onblocked = () =>
      reject(new Error("Close other War Room tabs and try again."));
  });
}

async function readWorkspace(): Promise<WorkspaceSnapshot | null> {
  const db = await database();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction(STORE, "readonly");
      const read = transaction.objectStore(STORE).get("current");
      transaction.oncomplete = () =>
        resolve(
          (read.result as StoredWorkspace | undefined)?.workspace ?? null,
        );
      transaction.onabort = () =>
        reject(new Error("Could not read your saved browser data."));
    });
  } finally {
    db.close();
  }
}

async function writeWorkspace(
  workspace: WorkspaceSnapshot | null,
  resetDrafts = false,
): Promise<void> {
  const db = await database();
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction(STORE, "readwrite");
      const store = transaction.objectStore(STORE);
      if (!workspace || resetDrafts) store.clear();
      if (workspace) store.put({ workspace }, "current");
      else store.delete("current");
      transaction.oncomplete = () => resolve();
      transaction.onabort = () =>
        reject(
          new Error(
            "Could not save to this browser. The operation is not saved. Free device storage and retry; export your existing backup first.",
          ),
        );
    });
  } finally {
    db.close();
  }
}

export async function withWorkspaceLock<T>(work: () => Promise<T>): Promise<T> {
  if (!navigator.locks || !window.indexedDB) {
    throw new Error(
      "Use a current browser over HTTPS or localhost with site storage enabled.",
    );
  }
  return navigator.locks.request(LOCK, work);
}

function encode(bytes: Uint8Array): string {
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 32768) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 32768));
  }
  return btoa(binary);
}

async function exchange(
  path: string,
  init: RequestInit | undefined,
  workspace: WorkspaceSnapshot | null,
) {
  const outgoing = new Request(location.origin + "/api/v1" + path, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...init?.headers,
    },
  });
  const response = await fetch("/api/v1/device", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    body: JSON.stringify({
      workspace,
      path: "/api/v1" + path,
      method: outgoing.method,
      body: encode(new Uint8Array(await outgoing.arrayBuffer())),
      content_type: outgoing.headers.get("content-type") || "application/json",
    }),
    signal: AbortSignal.timeout(30000),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : "Processing failed. Your saved browser data is unchanged.",
    );
  }
  const result = await response.json();
  if (!result.workspace || !Number.isInteger(result.status)) {
    throw new Error(
      "Invalid workspace response. Your saved browser data is unchanged.",
    );
  }
  return result as {
    status: number;
    result: unknown;
    workspace: WorkspaceSnapshot;
  };
}

export async function deviceRequest(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  return withWorkspaceLock(async () => {
    const account = await accountSession();
    if (account.expired)
      throw new Error(
        "Your account session expired. Open Profile & settings to log in again. Your cloud data is safe.",
      );
    if (account.user) {
      const outgoing = new Request(location.origin + "/api/v1" + path, {
        ...init,
        headers: {
          ...(init?.body instanceof FormData
            ? {}
            : { "Content-Type": "application/json" }),
          ...init?.headers,
        },
      });
      if (cloudRevision === undefined && outgoing.method !== "GET") {
        cloudRevision = (
          await cloudCall<{ revision: number }>(
            "/workspace",
            undefined,
            account.user.id,
          )
        ).revision;
      }
      const result = await cloudCall<{
        status: number;
        result: unknown;
        revision: number;
      }>(
        "/operation",
        {
          path: "/api/v1" + path,
          method: outgoing.method,
          expected_revision: outgoing.method === "GET" ? null : cloudRevision,
          body: encode(new Uint8Array(await outgoing.arrayBuffer())),
          content_type:
            outgoing.headers.get("content-type") || "application/json",
        },
        account.user.id,
      );
      cloudRevision = result.revision;
      return new Response(JSON.stringify(result.result), {
        status: result.status,
        headers: { "Content-Type": "application/json" },
      });
    }
    const current = await readWorkspace();
    const response = await exchange(path, init, current);
    // Commit before reporting success, and serialize across all tabs of this origin.
    await writeWorkspace(response.workspace);
    return new Response(JSON.stringify(response.result), {
      status: response.status,
      headers: { "Content-Type": "application/json" },
    });
  });
}

export async function exportWorkspace(): Promise<void> {
  const account = await accountSession();
  const workspace = account.user
    ? (
        await cloudCall<{ workspace: WorkspaceSnapshot | null }>(
          "/workspace",
          undefined,
          account.user.id,
        )
      ).workspace
    : await withWorkspaceLock(readWorkspace);
  if (!workspace) throw new Error("There is no saved workspace to export yet.");
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(workspace)], { type: "application/json" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = "interview-war-room-backup.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function refreshTabs() {
  const channel = new BroadcastChannel(LOCK);
  channel.postMessage("replaced");
  channel.close();
  location.replace(location.pathname + location.search);
}

export function watchWorkspaceReset(): () => void {
  const channel = new BroadcastChannel(LOCK);
  channel.onmessage = () =>
    location.replace(location.pathname + location.search);
  return () => channel.close();
}

export async function clearWorkspace(): Promise<void> {
  if ((await accountSession()).user)
    throw new Error(
      "Log out to delete guest device data. Use Delete account for cloud data.",
    );
  await withWorkspaceLock(() => writeWorkspace(null));
  refreshTabs();
}

export async function importWorkspace(file: File): Promise<void> {
  if ((await accountSession()).user)
    throw new Error(
      "Log out to restore a backup into the guest workspace, then import it into an empty account.",
    );
  if (file.size > MAX_BACKUP)
    throw new Error("Backup exceeds the 12 MB limit.");
  let workspace: WorkspaceSnapshot;
  try {
    workspace = JSON.parse(await file.text());
  } catch {
    throw new Error("This file is not a valid JSON backup.");
  }
  if (
    workspace?.version !== 1 ||
    workspace.schema_revision !== "0005" ||
    !workspace.tables
  ) {
    throw new Error(
      "Unsupported backup version. Your saved data is unchanged.",
    );
  }
  await withWorkspaceLock(async () => {
    const checked = await exchange("/profile", undefined, workspace);
    if (checked.status !== 200)
      throw new Error(
        "Backup could not be validated. Your saved data is unchanged.",
      );
    await writeWorkspace(checked.workspace, true);
  });
  refreshTabs();
}

export async function saveGuestToAccount(): Promise<void> {
  await withWorkspaceLock(async () => {
    const account = await accountSession();
    if (!account.user) throw new Error("Log in first.");
    const stored = await cloudCall<{ revision: number }>(
      "/workspace",
      undefined,
      account.user.id,
    );
    if (stored.revision !== 0)
      throw new Error(
        "Your account already has saved work. Guest import is only allowed into an empty account to prevent overwriting it.",
      );
    const workspace = await readWorkspace();
    if (!workspace)
      throw new Error("No guest workspace is saved in this browser.");
    await cloudCall("/workspace", { workspace, revision: 0 }, account.user.id);
  });
}

export async function answerDraft(
  turn: string,
  update?: { answer: string; revision: number },
): Promise<{ answer: string; revision: number }> {
  return withWorkspaceLock(async () => {
    const account = await accountSession();
    if (account.expired) throw new Error("Log in again to save this draft.");
    if (account.user) {
      if (!update)
        return cloudCall("/draft/" + turn, undefined, account.user.id);
      const result = await cloudCall<{ revision: number }>(
        "/draft",
        { turn_id: turn, ...update },
        account.user.id,
      );
      return { answer: update.answer, revision: result.revision };
    }
    const db = await database();
    try {
      return await new Promise((resolve, reject) => {
        const transaction = db.transaction(
          STORE,
          update ? "readwrite" : "readonly",
        );
        const store = transaction.objectStore(STORE);
        const read = store.get("draft:" + turn);
        let result = { answer: "", revision: 0 };
        read.onsuccess = () => {
          result = read.result || result;
          if (update) {
            if (update.revision !== result.revision) {
              transaction.abort();
              return;
            }
            result = { answer: update.answer, revision: result.revision + 1 };
            store.put(result, "draft:" + turn);
          }
        };
        transaction.oncomplete = () => resolve(result);
        transaction.onabort = () =>
          reject(
            new Error(
              "Draft changed in another tab or could not be saved. Copy your answer before reloading.",
            ),
          );
      });
    } finally {
      db.close();
    }
  });
}
