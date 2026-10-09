import { test, expect } from "@playwright/test";

test("AI status distinguishes configured, connected, unavailable and disabled", async ({
  page,
}) => {
  for (const [status, label] of Object.entries({
    unverified: "AI Connected",
    connected: "AI Connected",
    unavailable: "AI Disconnected",
    disabled: "AI Disconnected",
    mock: "AI Disconnected",
  })) {
    await page.route("**/api/v1/ai/status", (route) =>
      route.fulfill({ json: { status, model: "hidden-model" } }),
    );
    await page.goto("/");
    await expect(page.getByText(label, { exact: true })).toBeVisible();
    await expect(page.locator(".ai-status")).toHaveClass(
      label === "AI Connected" ? "ai-status connected" : "ai-status disconnected",
    );
    await expect(page.getByText("hidden-model")).toHaveCount(0);
    await page.unroute("**/api/v1/ai/status");
  }
});
