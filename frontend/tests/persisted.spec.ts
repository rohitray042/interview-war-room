import { test, expect } from "@playwright/test";

test("persisted M2/M3 data through a complete M4 interview, without document fixtures", async ({
  page,
  request,
}) => {
  test.skip(
    !process.env.WAR_ROOM_VERIFY_DATABASE,
    "Requires an explicit isolated copy of saved user data",
  );
  const offline = process.env.WAR_ROOM_VERIFY_OFFLINE === "1";
  const capabilities = await (await request.get("/api/v1/capabilities")).json();
  expect(capabilities.workspace.data).toBe("persisted-copy");
  expect(capabilities.workspace.simulated_ai).toBe(!offline);
  const targetsResponse = await request.get("/api/v1/targets");
  expect(targetsResponse.ok()).toBeTruthy();
  const targets = await targetsResponse.json();
  expect(targets.length).toBeGreaterThan(0);
  const target = targets[0];
  expect(target.result.method).toBe("evidence-comparison-v2");
  expect(target.result.items.length).toBeGreaterThan(0);
  const originalTarget = JSON.stringify(target);
  if (!offline) {
    const generated = await request.post("/api/v1/questions/generate", {
      data: { target_id: target.id, number_of_questions: 3 },
    });
    expect(generated.ok()).toBeTruthy();
    expect((await generated.json()).items).toHaveLength(3);
  }
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(
    page.getByText("Verification copy of saved user data.", { exact: false }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Mock interview", exact: true })
    .click();
  await page.getByLabel("Interview target JD").selectOption(target.id);
  await page.getByLabel("Primary questions").fill("3");
  await page
    .getByLabel("Question source")
    .selectOption(offline ? "curated" : "personalized");
  await page
    .getByRole("button", { name: "Start interview", exact: true })
    .click();
  await expect(
    page.getByText("Question 1 of 3", { exact: true }),
  ).toBeVisible();
  const identity = new URL(page.url()).hash.replace("#interview=", "");
  const url = `/api/v1/interviews/${identity}`;
  const answers = new Map<string, string>();
  for (let i = 0; i < (offline ? 3 : 9); i++) {
    const state = await (await request.get(url)).json();
    expect(state.configuration.target_id).toBe(target.id);
    const answer = `Integration verification answer ${i + 1}: I would validate source data, make incremental loads idempotent and test recovery before deployment.`;
    answers.set(state.current_turn.id, answer);
    await page.getByLabel("Your answer", { exact: true }).fill(answer);
    await page
      .getByRole("button", { name: "Submit answer", exact: true })
      .click();
    await expect(page.getByText("Answer saved", { exact: true })).toBeVisible();
    if (offline) {
      await expect(
        page.getByText(
          "AI evaluation is unavailable because no LLM provider is configured.",
          { exact: true },
        ),
      ).toBeVisible();
      await expect(
        page.getByRole("region", { name: "Answer evaluation" }),
      ).toHaveCount(0);
    } else {
      await expect(
        page.getByRole("region", { name: "Answer evaluation" }),
      ).toBeVisible();
    }
    if (i === 0 || i === 2) {
      await page.reload();
      await expect(page.locator(".saved-answer")).toHaveText(answer);
      const reloaded = await (await request.get(url)).json();
      expect(reloaded.current_turn.id).toBe(state.current_turn.id);
      expect(reloaded.current_turn.answer_text).toBe(answer);
    }
    if (offline)
      await page
        .getByRole("button", { name: "Continue unscored", exact: true })
        .click();
    const next = await (await request.get(url)).json();
    const name =
      next.next_action === "finish"
        ? "Finish interview"
        : next.next_action === "follow_up"
          ? "Ask follow-up"
          : "Next question";
    await page.getByRole("button", { name, exact: true }).click();
  }
  await expect(
    page.getByRole("region", { name: "Interview summary" }),
  ).toBeVisible();
  const summary = await (await request.get(url + "/summary")).json();
  expect(summary.session.id).toBe(identity);
  expect(summary.primary_answered).toBe(3);
  expect(summary.answers_submitted).toBe(answers.size);
  expect(summary.follow_ups).toBe(offline ? 0 : 6);
  for (const turn of summary.turns)
    expect(turn.answer_text).toBe(answers.get(turn.id));
  if (offline) {
    expect(summary.average_score).toBeNull();
    expect(summary.weak_areas).toEqual([]);
  } else {
    const scores = summary.turns.map(
      (t: { evaluation: { score: number } }) => t.evaluation.score,
    );
    expect(summary.average_score).toBe(
      scores.reduce((a: number, b: number) => a + b, 0) / scores.length,
    );
    const weaknesses = await (
      await request.get("/api/v1/interviews/weaknesses")
    ).json();
    const occurrences = weaknesses
      .flatMap(
        (w: { occurrences: { session_id: string; turn_id: string }[] }) =>
          w.occurrences,
      )
      .filter((o: { session_id: string }) => o.session_id === identity);
    expect(occurrences).toHaveLength(answers.size);
    for (const occurrence of occurrences)
      expect(answers.has(occurrence.turn_id)).toBeTruthy();
  }
  await page.reload();
  await expect(
    page.getByRole("region", { name: "Interview summary" }),
  ).toBeVisible();
  expect(await (await request.get(url + "/summary")).json()).toEqual(summary);
  expect(
    JSON.stringify(
      (await (await request.get("/api/v1/targets")).json()).find(
        (t: { id: string }) => t.id === target.id,
      ),
    ),
  ).toBe(originalTarget);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: `test-results/persisted-${offline ? "offline" : "mocked"}-mobile.png`,
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
