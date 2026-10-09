import { test, expect } from "@playwright/test";

test("AI status distinguishes configured, connected, unavailable and disabled", async ({
  page,
}) => {
  for (const [status, label] of Object.entries({
    unverified: "AI Unverified",
    connected: "AI Connected",
    unavailable: "AI Unavailable",
    disabled: "AI Disabled",
    mock: "AI Mock",
  })) {
    await page.route("**/api/v1/ai/status", (route) =>
      route.fulfill({ json: { status } }),
    );
    await page.goto("/");
    await expect(page.getByText(label, { exact: true })).toBeVisible();
    await page.unroute("**/api/v1/ai/status");
  }
});
