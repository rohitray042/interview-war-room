export type AccountSession = {
  enabled: boolean;
  expired?: boolean;
  user: { id: string; email: string } | null;
};
let session: Promise<AccountSession> | undefined;

export async function cloudCall<T>(
  path: string,
  body?: unknown,
  user?: string,
): Promise<T> {
  const response = await fetch("/api/v1/cloud" + path, {
    method: body === undefined ? "GET" : "POST",
    credentials: "same-origin",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(user ? { "X-Workspace-User": user } : {}),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    signal: AbortSignal.timeout(60000),
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Account request failed. Please retry.",
    );
  return data as T;
}
export function accountSession(): Promise<AccountSession> {
  return (session ??= cloudCall<AccountSession>("/session").catch((error) => {
    session = undefined;
    throw error;
  }));
}
export function accountChanged() {
  const channel = new BroadcastChannel("warroom-account");
  channel.postMessage("changed");
  channel.close();
  location.replace(location.pathname);
}
export function watchAccount() {
  const channel = new BroadcastChannel("warroom-account");
  channel.onmessage = () => location.replace(location.pathname);
  return () => channel.close();
}
