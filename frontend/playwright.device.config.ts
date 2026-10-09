import { defineConfig } from "@playwright/test";
import base from "./playwright.config";

export default defineConfig({
  ...base,
  testIgnore: [],
  testMatch: ["**/device-storage.spec.ts", "**/analyzer.spec.ts"],
  webServer: Array.isArray(base.webServer)
    ? base.webServer.map((server, index) =>
        index === 0
          ? {
              ...server,
              env: { ...process.env, WAR_ROOM_BROWSER_STORAGE: "browser" },
            }
          : server,
      )
    : base.webServer,
});
