import { test, expect } from "@playwright/test";

test("JD interview, persisted answers, two bounded follow-ups, completion and weakness evidence", async ({
  page,
  request,
}) => {
  const ids: string[] = [];
  for (const [kind, text] of [
    ["resume", "Interview Candidate\nSKILLS\nPython"],
    ["jd", "Must have\nKafka"],
  ]) {
    const response = await request.post("/api/v1/documents/text", {
      data: { kind, text },
    });
    const analysis = (await response.json()).analyses[0];
    await request.post(`/api/v1/analyses/${analysis.id}/confirm`, {
      data: { revision: analysis.revision },
    });
    ids.push(analysis.id);
  }
  const target = await request.post("/api/v1/targets", {
    data: { resume_id: ids[0], jd_id: ids[1] },
  });
  const targetId = (await target.json()).id;
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page
    .getByRole("button", { name: "Mock interview", exact: true })
    .click();
  await page.getByLabel("Interview target JD").selectOption(targetId);
  await page.getByLabel("Interview category").selectOption("Kafka");
  await page.getByLabel("Primary questions").fill("1");
  await page
    .getByRole("button", { name: "Start interview", exact: true })
    .click();
  await expect(
    page.getByText("Question 1 of 1", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Expected topics", { exact: true })).toHaveCount(
    0,
  );
  await expect(
    page.getByRole("region", { name: "Answer evaluation" }),
  ).toHaveCount(0);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({
    path: "test-results/interview-question-desktop.png",
    fullPage: true,
  });
  for (let depth = 0; depth < 3; depth++) {
    await page
      .getByLabel("Your answer", { exact: true })
      .fill(
        `Answer ${depth}: Use partition keys and idempotent writes; validate replay after a crash.`,
      );
    await page
      .getByRole("button", { name: "Submit answer", exact: true })
      .click();
    await expect(page.getByText("Answer saved", { exact: true })).toBeVisible();
    await expect(
      page.getByRole("region", { name: "Answer evaluation" }),
    ).toBeVisible();
    if (depth === 0) {
      await page.reload();
      await expect(
        page.getByText("Answer saved", { exact: true }),
      ).toBeVisible();
      await expect(page.locator(".saved-answer")).toContainText("Answer 0:");
    }
    if (depth < 2) {
      await page
        .getByRole("button", { name: "Ask follow-up", exact: true })
        .click();
      await expect(
        page.getByText(`Question 1 of 1 · Follow-up ${depth + 1} of 2`, {
          exact: true,
        }),
      ).toBeVisible();
    } else {
      await expect(
        page.getByRole("button", { name: "Ask follow-up", exact: true }),
      ).toHaveCount(0);
      await page
        .getByRole("button", { name: "Finish interview", exact: true })
        .click();
    }
  }
  const summary = page.getByRole("region", { name: "Interview summary" });
  await expect(
    summary.getByRole("heading", { name: "Interview complete" }),
  ).toBeVisible();
  await expect(summary).toContainText("Repeated review topics");
  await expect(summary).toContainText("3 assessments");
  await page.reload();
  await expect(summary).toBeVisible();
  await page.screenshot({
    path: "test-results/interview-summary-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "test-results/interview-summary-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Weaknesses", exact: true }).click();
  const weaknesses = page.getByRole("region", {
    name: "Evidence-based weaknesses",
  });
  await expect(weaknesses).toContainText("3 assessments");
  await weaknesses
    .getByRole("button", { name: /^Open topic/ })
    .first()
    .click();
  await expect(weaknesses).toContainText(
    "No supporting excerpt was identified",
  );
  expect(errors).toEqual([]);
});

test("evaluation network failure keeps the answer and permits explicit unscored completion", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Mock interview", exact: true })
    .click();
  await page.getByLabel("Interview category").selectOption("SQL");
  await page.getByLabel("Primary questions").fill("1");
  await page
    .getByRole("button", { name: "Start interview", exact: true })
    .click();
  await page.route("**/turns/*/evaluate", (route) => route.abort());
  await page
    .getByLabel("Your answer", { exact: true })
    .fill("A durable answer despite a network failure.");
  await page
    .getByRole("button", { name: "Submit answer", exact: true })
    .click();
  await expect(page.getByText("Answer saved", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.locator(".saved-answer")).toContainText("A durable answer");
  await expect(
    page.getByRole("button", { name: "Next question", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Continue unscored", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Finish interview", exact: true })
    .click();
  const summary = page.getByRole("region", { name: "Interview summary" });
  await expect(summary).toContainText("Not scored");
  await expect(summary).toContainText(
    "No evaluation-derived practice areas yet.",
  );
});
