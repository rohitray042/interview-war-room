import { test, expect, type Page } from "@playwright/test";

test("guest import, cloud saving on a second device, logout isolation and draft recovery", async ({
  page,
  browser,
}) => {
  let workspace: unknown = null;
  let revision = 0;
  const drafts = new Map<string, { answer: string; revision: number }>();
  async function accountService(target: Page) {
    let signedIn = false;
    await target.route("**/api/v1/cloud/**", async (route) => {
      const path = new URL(route.request().url()).pathname.split("/cloud")[1];
      const body =
        route.request().method() === "POST"
          ? route.request().postDataJSON()
          : {};
      const reply = (json: unknown, status = 200) =>
        route.fulfill({ json, status });
      if (path === "/session")
        return reply({
          enabled: true,
          user: signedIn
            ? { id: "test-account", email: "candidate@example.com" }
            : null,
        });
      if (path === "/login") {
        signedIn = true;
        return reply({ ok: true });
      }
      if (path === "/logout") {
        signedIn = false;
        return reply({ ok: true });
      }
      if (!signedIn) return reply({ detail: "Log in" }, 401);
      if (path.startsWith("/draft/"))
        return reply(drafts.get(path.slice(7)) || { answer: "", revision: 0 });
      if (path === "/draft") {
        const prior = drafts.get(body.turn_id) || { answer: "", revision: 0 };
        if (prior.revision !== body.revision)
          return reply({ detail: "Draft conflict" }, 409);
        drafts.set(body.turn_id, {
          answer: body.answer,
          revision: prior.revision + 1,
        });
        return reply({ revision: prior.revision + 1 });
      }
      if (path === "/workspace" && route.request().method() === "GET")
        return reply({ workspace, revision });
      if (path === "/workspace") {
        if (revision !== body.revision)
          return reply({ detail: "Conflict" }, 409);
        workspace = body.workspace;
        return reply({ revision: ++revision });
      }
      if (path === "/operation") {
        if (body.method !== "GET" && body.expected_revision !== revision)
          return reply({ detail: "Workspace conflict" }, 409);
        const { expected_revision: _, ...operation } = body;
        const processed = await target.request.post("/api/v1/device", {
          data: { ...operation, workspace },
        });
        const result = await processed.json();
        if (body.method !== "GET") {
          workspace = result.workspace;
          revision++;
        }
        return reply({
          status: result.status,
          result: result.result,
          revision,
        });
      }
      return reply({ answer: "", revision: 0 });
    });
  }
  async function profile(target: Page) {
    await target
      .getByRole("button", { name: "Profile & settings", exact: true })
      .click();
  }
  async function signIn(target: Page) {
    const account = target.getByRole("region", {
      name: "Account and cloud saving",
    });
    await account
      .getByLabel("Email", { exact: true })
      .fill("candidate@example.com");
    await account
      .getByLabel("Password", { exact: true })
      .fill("synthetic-password");
    await account
      .getByRole("button", { name: "Log in", exact: true })
      .last()
      .click();
    await expect(
      target.getByText("Saved to your private account.", { exact: true }),
    ).toBeVisible();
  }
  await accountService(page);
  await page.goto("/");
  await profile(page);
  await page.getByLabel("Name", { exact: true }).fill("Guest Candidate");
  await page.getByRole("button", { name: "Save profile", exact: true }).click();
  await expect(page.getByText("Profile saved", { exact: true })).toBeVisible();
  await signIn(page);
  await profile(page);
  // Login has not silently uploaded the guest workspace.
  await expect(page.getByLabel("Name", { exact: true })).toHaveValue("");
  expect(workspace).toBeNull();
  page.once("dialog", (dialog) => dialog.accept());
  await Promise.all([
    page.waitForEvent("domcontentloaded"),
    page.getByRole("button", { name: "Import guest progress" }).click(),
  ]);
  await expect(
    page.getByText("Saved to your private account.", { exact: true }),
  ).toBeVisible();
  await profile(page);
  await expect(page.getByLabel("Name", { exact: true })).toHaveValue(
    "Guest Candidate",
  );
  await page.getByLabel("Name", { exact: true }).fill("Cloud Candidate");
  await page.getByRole("button", { name: "Save profile", exact: true }).click();
  await expect(page.getByText("Profile saved", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Mock interview", exact: true })
    .click();
  await page.getByLabel("Interview category").selectOption("SQL");
  await page.getByLabel("Primary questions").fill("1");
  await page
    .getByRole("button", { name: "Start interview", exact: true })
    .click();
  await page
    .getByLabel("Your answer", { exact: true })
    .fill("My cross-device draft uses an INNER JOIN.");
  await expect(page.getByText("Draft saved", { exact: true })).toBeVisible();
  const interviewHash = new URL(page.url()).hash;
  const phone = await browser.newContext({
    viewport: { width: 390, height: 844 },
  });
  const phonePage = await phone.newPage();
  await accountService(phonePage);
  await phonePage.goto("/");
  await profile(phonePage);
  await phonePage.screenshot({
    path: "test-results/account-login-phone.png",
    fullPage: true,
  });
  await signIn(phonePage);
  await profile(phonePage);
  await expect(phonePage.getByLabel("Name", { exact: true })).toHaveValue(
    "Cloud Candidate",
  );
  await phonePage.goto("/" + interviewHash);
  await expect(
    phonePage.getByLabel("Your answer", { exact: true }),
  ).toHaveValue("My cross-device draft uses an INNER JOIN.");
  await expect(
    phonePage.getByText("Draft restored", { exact: true }),
  ).toBeVisible();
  await phonePage.screenshot({
    path: "test-results/account-phone.png",
    fullPage: true,
  });
  await profile(page);
  await page.getByRole("button", { name: "Log out", exact: true }).click();
  await expect(
    page.getByText("Saved in this browser.", { exact: true }),
  ).toBeVisible();
  await profile(page);
  await expect(page.getByLabel("Name", { exact: true })).toHaveValue(
    "Guest Candidate",
  );
  await phone.close();
});
