import { deviceRequest } from "./deviceStorage";

export interface Profile {
  id: string;
  name: string;
  background: string;
  target_role: string;
  skills: string[];
  learning_skills: string[];
  daily_study_minutes: number;
}
export interface Manifest {
  questions: {
    id: string;
    version: number;
    topic: string;
    difficulty: string;
    type: string;
  }[];
  rubrics: { id: string; version: number }[];
}
let storage: Promise<"browser" | "local_sqlite"> | undefined;
export function storageMode(): Promise<"browser" | "local_sqlite"> {
  if (!storage) {
    storage = fetch("/api/v1/storage", {
      cache: "no-store",
      signal: AbortSignal.timeout(10000),
    })
      .then(async (response) => {
        if (!response.ok)
          throw new Error(
            "Could not verify workspace storage. Check the backend connection.",
          );
        const value = await response.json();
        if (value.mode !== "browser" && value.mode !== "local_sqlite")
          throw new Error("Unknown storage mode.");
        return value.mode;
      })
      .catch((error) => {
        storage = undefined;
        throw error;
      });
  }
  return storage!;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const publicRead =
    (!init?.method || init.method === "GET") &&
    ["/health", "/capabilities", "/ai/status", "/content/manifest"].includes(
      path,
    );
  const response =
    (await storageMode()) === "browser" && !publicRead
      ? await deviceRequest(path, init)
      : await fetch("/api/v1" + path, {
          ...init,
          headers: {
            ...(init?.body instanceof FormData
              ? {}
              : { "Content-Type": "application/json" }),
            ...init?.headers,
          },
          signal: AbortSignal.timeout(30000),
        });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : response.status === 422
          ? "Check your fields and try again."
          : "The local API could not complete this request. Check that the backend is running.",
    );
  }
  return response.json() as Promise<T>;
}
