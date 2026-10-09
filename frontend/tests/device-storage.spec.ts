import { test, expect, type Page } from "@playwright/test";

test("fresh AI interview starts without a target or saved generated questions", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Mock interview", exact: true })
    .click();
  await page
    .getByLabel("Question source", { exact: true })
    .selectOption("ai_generated");
  await page.getByLabel("Interview category").selectOption("Snowflake");
  await page.getByLabel("Interview difficulty").selectOption("easy");
  await page
    .getByLabel("Question type", { exact: true })
    .selectOption("coding");
  await page.getByLabel("Primary questions").fill("1");
  await expect(page.getByText("Ready for fresh AI questions")).toBeVisible();
  await page
    .getByRole("button", { name: "Start interview", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: /Given a hypothetical workload/ }),
  ).toBeVisible();
  await expect(
    page.getByText("General practice · Snowflake · Easy"),
  ).toBeVisible();
  const identity = new URL(page.url()).hash;
  await page
    .getByLabel("Your answer", { exact: true })
    .fill(
      "Use an isolated warehouse and measure credit usage and query latency.",
    );
  await page
    .getByRole("button", { name: "Submit answer", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Answer evaluation" }),
  ).toBeVisible();
  await page.reload();
  expect(new URL(page.url()).hash).toBe(identity);
  await expect(page.getByText("Answer saved", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Ask follow-up", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: /For Snowflake, explain Recovery/ }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/fresh-interview-mobile.png",
    fullPage: true,
  });
});

async function api(
  page: Page,
  path: string,
  init?: { method: string; body: string },
) {
  return page.evaluate(
    async ({ path, init }) => {
      const { request } = await import("/src/api.ts");
      return request(path, init);
    },
    { path, init },
  );
}

async function documents(page: Page) {
  return api(page, "/documents") as Promise<{ id: string; filename: string }[]>;
}

test("two browser profiles, same-origin tabs, reload, backup and delete remain isolated", async ({
  browser,
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText("Saved in this browser.")).toBeVisible();
  await page.getByRole("button", { name: "Resume & JD", exact: true }).click();
  await page.getByLabel("Upload resume file").setInputFiles({
    name: "alice-private.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(
      "Alice Private\nSKILLS\nSQL, Python\nEXPERIENCE\nBuilt data pipelines.",
    ),
  });
  await expect.poll(async () => (await documents(page)).length).toBe(1);
  const aliceDocument = (await documents(page))[0];
  const other = await browser.newContext();
  try {
    const bob = await other.newPage();
    await bob.goto("/");
    expect(await documents(bob)).toEqual([]);
    expect(await api(bob, "/interviews")).toEqual([]);
    const leaked = await bob.evaluate(async (id) => {
      const { request } = await import("/src/api.ts");
      try {
        await request("/documents/" + id);
        return true;
      } catch {
        return false;
      }
    }, aliceDocument.id);
    expect(leaked).toBe(false);
    const direct = await bob.request.get(
      "/api/v1/documents/" + aliceDocument.id,
    );
    expect(direct.status()).toBe(403);

    const second = await page.context().newPage();
    await second.goto("/");
    await Promise.all([
      api(page, "/documents/text", {
        method: "POST",
        body: JSON.stringify({
          kind: "jd",
          text: "Must have\nSQL",
          filename: "target-one.txt",
        }),
      }),
      api(second, "/documents/text", {
        method: "POST",
        body: JSON.stringify({
          kind: "jd",
          text: "Must have\nKafka",
          filename: "target-two.txt",
        }),
      }),
    ]);
    await page.reload();
    expect((await documents(page)).length).toBe(3);
    expect(await documents(bob)).toEqual([]);

    await page.getByRole("button", { name: "Profile & settings" }).click();
    await page.getByLabel("Name", { exact: true }).fill("Alice");
    await page.getByRole("button", { name: "Save profile" }).click();
    await expect(page.getByRole("status")).toHaveText("Profile saved");
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Export backup" }).click();
    const file = await (await download).path();
    expect(file).toBeTruthy();
    await page.setViewportSize({ width: 390, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: "test-results/device-privacy-mobile.png",
      fullPage: true,
    });

    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "Delete device data" }).click();
    await expect(
      page.getByRole("heading", { name: "Your next chapter starts here." }),
    ).toBeVisible();
    expect(await documents(page)).toEqual([]);
    expect(await documents(second)).toEqual([]);
    await page.getByRole("button", { name: "Profile & settings" }).click();
    page.once("dialog", (dialog) => dialog.accept());
    await page
      .locator('section[aria-label="Device privacy"] input[type="file"]')
      .setInputFiles(file!);
    await expect(
      page.getByRole("heading", { name: "Your next chapter, Alice." }),
    ).toBeVisible();
    expect((await documents(page)).length).toBe(3);
    expect(await documents(bob)).toEqual([]);
    await second.close();
  } finally {
    await other.close();
  }
});

test("saved answers survive refresh and AI failure; duplicate submissions save once", async ({
  page,
}) => {
  await page.goto("/");
  let state: any = await api(page, "/interviews", {
    method: "POST",
    body: JSON.stringify({
      request_id: "browser-private-session",
      number_of_questions: 1,
      category: "Kafka",
    }),
  });
  const url = "/interviews/" + state.id;
  state = await api(page, url + "/actions", {
    method: "POST",
    body: JSON.stringify({ revision: state.revision, action: "start" }),
  });
  const answerUrl = url + "/turns/" + state.current_turn.id + "/answer";
  const answer = {
    method: "POST",
    body: JSON.stringify({
      revision: state.revision,
      submission_id: "private-answer-id",
      answer_text:
        "Partition keys preserve ordering; replay requires idempotent writes.",
    }),
  };
  await Promise.all([
    api(page, answerUrl, answer),
    api(page, answerUrl, answer),
  ]);
  await page.goto("/#interview=" + state.id);
  await expect(page.getByText("Answer saved", { exact: true })).toBeVisible();
  await page.reload();
  await expect(
    page.getByText(
      "Partition keys preserve ordering; replay requires idempotent writes.",
      { exact: true },
    ),
  ).toBeVisible();
  expect(((await api(page, "/interviews/stats")) as any).answers).toBe(1);
  await page.route("**/api/v1/device", (route) => {
    const payload = route.request().postDataJSON();
    return payload.path.endsWith("/evaluate")
      ? route.abort()
      : route.continue();
  });
  await expect(
    api(page, answerUrl.replace("/answer", "/evaluate"), {
      method: "POST",
      body: "{}",
    }),
  ).rejects.toThrow();
  await page.unroute("**/api/v1/device");
  const evaluated: any = await api(
    page,
    answerUrl.replace("/answer", "/evaluate"),
    { method: "POST", body: "{}" },
  );
  expect(evaluated.current_turn.evaluation.score).toBe(5);
  expect(((await api(page, "/interviews/stats")) as any).answers).toBe(1);
});

test("storage failure never reports save success or falls back to shared server data", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText("Saved in this browser.")).toBeVisible();
  await page.getByRole("button", { name: "Profile & settings" }).click();
  await page.getByLabel("Name", { exact: true }).fill("Must not claim saved");
  await page.evaluate(() => {
    const original = IDBDatabase.prototype.transaction;
    IDBDatabase.prototype.transaction = function (...args: any[]) {
      if (args[1] === "readwrite")
        throw new DOMException("Storage full", "QuotaExceededError");
      return original.apply(this, args as any);
    } as typeof original;
  });
  await page.getByRole("button", { name: "Save profile" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByText("Profile saved", { exact: true })).toHaveCount(0);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Your next chapter starts here." }),
  ).toBeVisible();
});
