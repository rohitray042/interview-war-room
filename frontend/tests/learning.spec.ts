import { test, expect } from "@playwright/test";

test("LLM-disabled learning preserves stored evidence and honest empty states", async ({
  page,
  request,
}) => {
  test.skip(
    process.env.WAR_ROOM_VERIFY_OFFLINE !== "1",
    "Run with the disabled-provider test server",
  );
  const before = await (await request.get("/api/v1/weaknesses")).json();
  const cap = await (await request.get("/api/v1/capabilities")).json();
  expect(cap.interview_evaluation.enabled).toBe(false);
  await page.goto("/#weaknesses=all");
  await expect(
    page.getByRole("heading", { name: "Learning signals" }),
  ).toBeVisible();
  if (!before.items.length)
    await expect(
      page.getByText(
        "No evaluation-derived review topics yet for these filters.",
        { exact: true },
      ),
    ).toBeVisible();
  await page.reload();
  expect(await (await request.get("/api/v1/weaknesses")).json()).toEqual(
    before,
  );
  await expect(
    page.getByText("AI evaluation disabled.", { exact: false }),
  ).toBeVisible();
});

test("evidence to exact-topic M3 practice, M4 retest, improvement and refresh", async ({
  page,
  request,
}) => {
  test.skip(
    process.env.WAR_ROOM_VERIFY_OFFLINE === "1",
    "Successful evaluation requires the isolated fake provider",
  );
  let target: string;
  if (process.env.WAR_ROOM_VERIFY_DATABASE) {
    const targets = await (await request.get("/api/v1/targets")).json();
    expect(targets.length).toBeGreaterThan(0);
    target = targets[0].id;
  } else {
    const analyses = [];
    for (const [kind, text] of [
      ["resume", "Learning verification candidate\nSKILLS\nPython"],
      ["jd", "Must have\nKafka"],
    ]) {
      const r = await request.post("/api/v1/documents/text", {
        data: { kind, text },
      });
      const a = (await r.json()).analyses[0];
      expect(
        (
          await request.post(`/api/v1/analyses/${a.id}/confirm`, {
            data: { revision: a.revision },
          })
        ).ok(),
      ).toBeTruthy();
      analyses.push(a.id);
    }
    const r = await request.post("/api/v1/targets", {
      data: { resume_id: analyses[0], jd_id: analyses[1] },
    });
    target = (await r.json()).id;
  }
  const created = await request.post("/api/v1/interviews", {
    data: {
      request_id: crypto.randomUUID(),
      target_id: target,
      number_of_questions: 1,
    },
  });
  expect(created.ok()).toBeTruthy();
  let session = await created.json();
  const url = `/api/v1/interviews/${session.id}`;
  async function act(action: string) {
    const r = await request.post(url + "/actions", {
      data: { action, revision: session.revision },
    });
    expect(r.ok()).toBeTruthy();
    session = await r.json();
  }
  await act("start");
  while (session.status === "active") {
    const turnUrl = `${url}/turns/${session.current_turn.id}`;
    const answer = await request.post(turnUrl + "/answer", {
      data: {
        revision: session.revision,
        submission_id: crypto.randomUUID(),
        answer_text:
          "Verification answer: I would validate input and retry safely.",
      },
    });
    expect(answer.ok()).toBeTruthy();
    const evaluation = await request.post(turnUrl + "/evaluate", { data: {} });
    expect(evaluation.ok()).toBeTruthy();
    session = await evaluation.json();
    await act(session.next_action === "finish" ? "finish" : "next");
  }
  const rows = await (await request.get("/api/v1/weaknesses")).json();
  const row = rows.items.find(
    (v: { occurrence_count: number; timeline: { session_id: string }[] }) =>
      v.occurrence_count > 0 &&
      v.timeline.some((p) => p.session_id === session.id),
  );
  expect(row).toBeTruthy();
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByRole("button", { name: "Weaknesses", exact: true }).click();
  await page.getByLabel("Learning target JD").selectOption(target);
  await page.getByLabel("Search learning topics").fill(row.topic);
  await page
    .getByRole("button", { name: `Open topic ${row.topic}`, exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Learning evidence", exact: true }),
  ).toContainText("No supporting excerpt was identified");
  await expect(
    page.getByRole("region", { name: "JD relevance", exact: true }),
  ).toContainText("selected JD");
  await page.reload();
  await expect(
    page.getByRole("heading", { name: row.topic, exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Practice This", exact: true })
    .click();
  const bank = page.getByRole("region", { name: "Question bank", exact: true });
  await expect(
    bank.getByRole("heading", { name: `Practice: ${row.topic}`, exact: true }),
  ).toBeVisible();
  const qs = await (
    await request.get(`/api/v1/questions?focus_id=${row.id}&source=curated`)
  ).json();
  expect(qs.items.length).toBeGreaterThan(0);
  await expect(bank.locator(".question-open")).toHaveCount(qs.items.length);
  await bank.locator(".question-open").first().click();
  await expect(
    page.getByRole("region", { name: "Question details" }),
  ).toContainText("Expected topics");
  await page.reload();
  await expect(
    bank.getByRole("heading", { name: `Practice: ${row.topic}`, exact: true }),
  ).toBeVisible();
  await bank
    .getByRole("button", { name: "Start targeted interview", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Begin saved interview", exact: true })
    .click();
  await page
    .getByLabel("Your answer", { exact: true })
    .fill(
      "[verification:strong] I would validate invariants, monitor failures, test idempotency and explain the operational trade-offs.",
    );
  await page
    .getByRole("button", { name: "Submit answer", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Answer evaluation" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Finish interview", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Interview summary" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Review learning signal" }).click();
  await expect(
    page.getByText("Improvement detected in later interview evidence.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Performance trend" }),
  ).toContainText("Strong");
  const final = await (
    await request.get(`/api/v1/weaknesses/${row.id}`)
  ).json();
  expect(final.status).toBe("improving");
  expect(final.timeline.length).toBeGreaterThanOrEqual(2);
  await page.reload();
  await expect(
    page.getByText("Improvement detected in later interview evidence.", {
      exact: true,
    }),
  ).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({
    path: "test-results/learning-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "test-results/learning-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});
