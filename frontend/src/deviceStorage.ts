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
): Promise<void> {
  const db = await database();
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction(STORE, "readwrite");
      const store = transaction.objectStore(STORE);
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
  const workspace = await withWorkspaceLock(readWorkspace);
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
  await withWorkspaceLock(() => writeWorkspace(null));
  refreshTabs();
}

export async function importWorkspace(file: File): Promise<void> {
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
    await writeWorkspace(checked.workspace);
  });
  refreshTabs();
}
