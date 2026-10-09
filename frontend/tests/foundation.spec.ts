import { test, expect } from "@playwright/test";

test("real API, profile persistence, theme, desktop and mobile layout", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewportSize({ width: 1440, height: 1050 });
  await page.goto("/");
  await expect(page.getByText("3 sample questions loaded")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Mock interview" }),
  ).toBeEnabled();
  await expect(page.getByText("Not assessed yet")).toBeVisible();
  await page.screenshot({
    path: "test-results/overview-desktop.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Set up your profile" }).click();
  await page.getByLabel("Name", { exact: true }).fill("Test Candidate");
  await page.getByLabel("Target role").fill("Senior Data Engineer");
  await page
    .getByLabel("Current skills", { exact: true })
    .pressSequentially("SQL, Apache Spark");
  await page.getByLabel("Daily study time").fill("90");
  await page.getByRole("button", { name: "Save profile" }).click();
  await expect(page.getByRole("status")).toHaveText("Profile saved");
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Your next chapter, Test." }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Edit preparation profile" }).click();
  await expect(page.getByLabel("Current skills", { exact: true })).toHaveValue(
    "SQL, Apache Spark",
  );
  await expect(page.getByLabel("Daily study time")).toHaveValue("90");
  await page.getByRole("button", { name: "Use dark theme" }).click();
  await page.screenshot({
    path: "test-results/profile-dark.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "test-results/profile-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});

test("API failure is visible and recoverable", async ({ page }) => {
  await page.route("**/api/v1/profile", (r) =>
    r.fulfill({ status: 503, body: "{}" }),
  );
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("local API");
  await page.unroute("**/api/v1/profile");
  await page.getByRole("button", { name: "Reconnect" }).click();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.getByText("3 sample questions loaded")).toBeVisible();
});
