import { test, expect } from "@playwright/test";

test("navigation and AI metadata fit mobile, tablet and desktop", async ({
  page,
}) => {
  await page.route("**/api/v1/ai/status", (route) =>
    route.fulfill({
      json: {
        status: "unavailable",
        provider: "gemini",
        model: "gemini-3.5-flash-lite",
      },
    }),
  );
  await page.goto("/");
  await expect(page.locator(".ai-status")).toContainText(
    "AI Disconnected",
  );
  for (const width of [320, 390, 560, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const name of [
      "Overview",
      "Resume & JD",
      "Question bank",
      "Mock interview",
      "Weaknesses",
      "Profile & settings",
    ]) {
      await page.getByRole("button", { name, exact: true }).click();
      await expect(page.locator(".breadcrumbs")).toContainText(
        name === "Profile & settings" ? "Profile" : name,
      );
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      const breadcrumb = await page.locator(".breadcrumbs").boundingBox();
      const actions = await page.locator(".header-actions").boundingBox();
      expect(
        breadcrumb &&
          actions &&
          (breadcrumb.y + breadcrumb.height <= actions.y ||
            breadcrumb.x + breadcrumb.width <= actions.x),
      ).toBeTruthy();
    }
    await page.screenshot({
      path: `test-results/responsive-${width}.png`,
      fullPage: true,
    });
  }
});
