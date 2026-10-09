import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Pause,
  Play,
  RefreshCw,
  Send,
  Square,
} from "lucide-react";
import { request } from "./api";
import "./interview.css";

type Evidence = { start: number; end: number; quote: string };
type Rating = { dimension: string; score: number; evidence: Evidence[] };
type Evaluation = {
  id: string;
  score: number;
  strengths: string[];
  weaknesses: string[];
  missing_points: string[];
  feedback: string;
  rubric_results: Rating[];
  follow_up_required: boolean;
  follow_up_reason: string | null;
};
type Turn = {
  id: string;
  primary_number: number;
  follow_up_depth: number;
  parent_turn_id: string | null;
  question_text: string;
  category: string;
  difficulty: string;
  answer_text: string | null;
  evaluation_state: string;
  evaluation_error: string | null;
  retryable: boolean;
  evaluation: Evaluation | null;
};
type Config = {
  focus_id?: string | null;
  target_id: string | null;
  interview_type: string;
  category: string | null;
  difficulty: string | null;
  question_type?: string | null;
  number_of_questions: number;
  source: string;
  allow_external_processing: boolean;
};
type SessionCard = {
  id: string;
  status: string;
  revision: number;
  configuration: Config;
  total_questions: number;
  created_at: string;
};
type Interview = SessionCard & {
  current_turn: Turn | null;
  answered_turns: number;
  resolved_primary_questions: number;
  next_action: string;
};
export type Weakness = {
  skill: string;
  topic: string;
  count: number;
  occurrences: {
    session_id: string;
    turn_id: string;
    evaluation_id: string;
    primary_number: number;
    follow_up_depth: number;
    assessment: string;
    evidence: Evidence[];
  }[];
};
type Summary = {
  session: SessionCard;
  primary_questions: number;
  primary_answered: number;
  answers_submitted: number;
  evaluations_completed: number;
  unscored_answers: number;
  average_score: number | null;
  primary_average_score: number | null;
  follow_ups: number;
  strong_areas: string[];
  weak_areas: Weakness[];
  suggested_practice: string[];
  review_turn_ids: string[];
  turns: Turn[];
};
type Target = {
  id: string;
  created_at: string;
  result: { items: { topic: string }[] };
};
const types = [
  "technical",
  "sql",
  "data_engineering",
  "system_design",
  "behavioral",
  "project_deep_dive",
  "mixed",
];
const sources = ["curated", "personalized", "ai_generated", "mixed"];
const label = (s: string) =>
  s.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
const defaults: Config = {
  target_id: null,
  interview_type: "technical",
  category: null,
  difficulty: null,
  number_of_questions: 5,
  source: "curated",
  allow_external_processing: false,
};

function Feedback({ value }: { value: Evaluation }) {
  return (
    <section className="interview-feedback" aria-label="Answer evaluation">
      <div className="interview-score">
        <strong>
          {value.score.toFixed(1)}
          <small> / 10</small>
        </strong>
        <span>Answer assessment</span>
      </div>
      <div className="feedback-columns">
        {[
          ["Strengths", value.strengths],
          ["Needs improvement", value.weaknesses],
          ["Not demonstrated", value.missing_points],
        ].map(([title, entries]) => (
          <div key={title as string}>
            <h3>{title as string}</h3>
            {(entries as string[]).length ? (
              <ul>
                {(entries as string[]).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : (
              <p>None identified in this assessment.</p>
            )}
          </div>
        ))}
      </div>
      <p>{value.feedback}</p>
      <details>
        <summary>Rubric breakdown and answer evidence</summary>
        {value.rubric_results.map((r) => (
          <div className="rubric-result" key={r.dimension}>
            <h4>
              {label(r.dimension)} · {r.score}/4
            </h4>
            {r.evidence.map((e, i) => (
              <blockquote key={i}>
                {e.quote}
                <cite>
                  Answer characters {e.start}–{e.end}
                </cite>
              </blockquote>
            ))}
            {!r.evidence.length && <p>No supporting excerpt identified.</p>}
          </div>
        ))}
      </details>
      {value.follow_up_reason && <p>{value.follow_up_reason}</p>}
    </section>
  );
}

export default function MockInterview() {
  const [sessions, setSessions] = useState<SessionCard[]>([]),
    [targets, setTargets] = useState<Target[]>([]),
    [categories, setCategories] = useState<string[]>([]);
  const [current, setCurrent] = useState<Interview | null>(null),
    [summary, setSummary] = useState<Summary | null>(null);
  const [config, setConfig] = useState<Config>(defaults),
    [available, setAvailable] = useState<number | null>(null),
    [previewError, setPreviewError] = useState("");
  const [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [draft, setDraft] = useState("");
  const [consent, setConsent] = useState(false),
    [capability, setCapability] = useState({ enabled: false, external: false });
  const [generationEnabled, setGenerationEnabled] = useState(false);
  const [questionTypes, setQuestionTypes] = useState<string[]>([]);
  const createKey = useRef(crypto.randomUUID()),
    submission = useRef({ turn: "", key: crypto.randomUUID() }),
    busyRef = useRef(false),
    questionRef = useRef<HTMLHeadingElement>(null);
  async function loadSession(id: string) {
    const next = await request<Interview>("/interviews/" + id);
    setCurrent(next);
    setConsent(next.configuration.allow_external_processing);
    history.replaceState(null, "", "#interview=" + id);
    setSummary(
      ["completed", "abandoned"].includes(next.status)
        ? await request<Summary>("/interviews/" + id + "/summary")
        : null,
    );
    return next;
  }
  async function load() {
    setLoading(true);
    setError("");
    try {
      const [list, ts, metadata, cap] = await Promise.all([
        request<SessionCard[]>("/interviews"),
        request<Target[]>("/targets"),
        request<{ category: string[]; question_type: string[] }>(
          "/interviews/options",
        ),
        request<{
          interview_evaluation: { enabled: boolean; external: boolean };
          question_generation: { enabled: boolean };
        }>("/capabilities"),
      ]);
      setSessions(list);
      setTargets(ts);
      setCategories(metadata.category);
      setQuestionTypes(metadata.question_type);
      setGenerationEnabled(cap.question_generation.enabled);
      setCapability(cap.interview_evaluation);
      const selected = new URLSearchParams(location.hash.slice(1)).get(
        "interview",
      );
      if (selected) await loadSession(selected);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void load();
  }, []);
  useEffect(() => {
    let active = true;
    if (current) return;
    setAvailable(null);
    setPreviewError("");
    const timer = setTimeout(() => {
      request<{ available: number }>("/interviews/preview", {
        method: "POST",
        body: JSON.stringify({ ...config, request_id: createKey.current }),
      })
        .then((result) => {
          if (active) setAvailable(result.available);
        })
        .catch((e) => {
          if (active) setPreviewError(e.message);
        });
    }, 180);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [config, current?.id]);
  useEffect(() => {
    setDraft("");
    if (current?.current_turn)
      submission.current = {
        turn: current.current_turn.id,
        key: crypto.randomUUID(),
      };
    questionRef.current?.focus();
  }, [current?.current_turn?.id]);
  useEffect(() => {
    const protect = (e: BeforeUnloadEvent) => {
      if (draft.trim() && !current?.current_turn?.answer_text) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", protect);
    return () => window.removeEventListener("beforeunload", protect);
  }, [draft, current?.current_turn?.answer_text]);
  useEffect(() => {
    if (!current || current.current_turn?.evaluation_state !== "evaluating")
      return;
    const timer = setInterval(() => {
      request<Interview>("/interviews/" + current.id)
        .then(setCurrent)
        .catch((e) => setError(e.message));
    }, 1500);
    return () => clearInterval(timer);
  }, [current?.id, current?.current_turn?.evaluation_state]);
  function edit<K extends keyof Config>(key: K, value: Config[K]) {
    createKey.current = crypto.randomUUID();
    setConfig({ ...config, [key]: value });
  }
  async function run(work: () => Promise<void>) {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError("");
    try {
      await work();
    } catch (e) {
      setError((e as Error).message);
      if (current) {
        try {
          setCurrent(await request<Interview>("/interviews/" + current.id));
        } catch {
          /* Keep the saved local view on connection failure. */
        }
      }
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }
  async function start() {
    const created = await request<Interview>("/interviews", {
      method: "POST",
      body: JSON.stringify({ ...config, request_id: createKey.current }),
    });
    setCurrent(created);
    history.replaceState(null, "", "#interview=" + created.id);
    if (created.status === "not_started") {
      const started = await request<Interview>(
        "/interviews/" + created.id + "/actions",
        {
          method: "POST",
          body: JSON.stringify({ revision: created.revision, action: "start" }),
        },
      );
      setCurrent(started);
    }
    setConsent(config.allow_external_processing);
    createKey.current = crypto.randomUUID();
  }
  async function action(name: string) {
    if (!current) return;
    const next = await request<Interview>(
      "/interviews/" + current.id + "/actions",
      {
        method: "POST",
        body: JSON.stringify({ revision: current.revision, action: name }),
      },
    );
    setCurrent(next);
    if (["completed", "abandoned"].includes(next.status))
      setSummary(
        await request<Summary>("/interviews/" + current.id + "/summary"),
      );
  }
  async function evaluate(state: Interview) {
    setCurrent(
      await request<Interview>(
        `/interviews/${state.id}/turns/${state.current_turn!.id}/evaluate`,
        {
          method: "POST",
          body: JSON.stringify({ allow_external_processing: consent }),
        },
      ),
    );
  }
  async function answer() {
    if (!current?.current_turn) return;
    const saved = await request<Interview>(
      `/interviews/${current.id}/turns/${current.current_turn.id}/answer`,
      {
        method: "POST",
        body: JSON.stringify({
          revision: current.revision,
          submission_id: submission.current.key,
          answer_text: draft,
        }),
      },
    );
    setCurrent(saved);
    setDraft("");
    await evaluate(saved);
  }
  async function back() {
    if (
      draft.trim() &&
      !current?.current_turn?.answer_text &&
      !window.confirm("Leave this unsaved draft?")
    )
      return;
    setCurrent(null);
    setSummary(null);
    setDraft("");
    history.replaceState(null, "", location.pathname + location.search);
    setSessions(await request<SessionCard[]>("/interviews"));
  }
  const turn = current?.current_turn;
  const closed = current && ["completed", "abandoned"].includes(current.status);
  return (
    <section className="mock-interview" aria-label="Mock interview workspace">
      {error && (
        <div className="error" role="alert">
          {error}
          <button onClick={() => void load()}>Reload saved state</button>
        </div>
      )}
      {loading ? (
        <p role="status">Loading interviews...</p>
      ) : !current ? (
        <>
          <form
            className="interview-setup"
            onSubmit={(e) => {
              e.preventDefault();
              void run(start);
            }}
          >
            <div className="interview-section-heading">
              <h2>Configure an interview</h2>
              <span>Text interview · Up to 2 follow-ups per question</span>
            </div>
            <div className="interview-fields">
              <label>
                Target JD
                <select
                  aria-label="Interview target JD"
                  value={config.target_id || ""}
                  onChange={(e) => edit("target_id", e.target.value || null)}
                >
                  <option value="">General practice</option>
                  {targets.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.result.items
                        .slice(0, 3)
                        .map((i) => i.topic)
                        .join(", ")}{" "}
                      · {new Date(t.created_at).toLocaleDateString()} ·{" "}
                      {t.id.slice(0, 8)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Interview type
                <select
                  aria-label="Interview type"
                  value={config.interview_type}
                  onChange={(e) => edit("interview_type", e.target.value)}
                >
                  {types.map((t) => (
                    <option key={t} value={t}>
                      {label(t)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Category
                <select
                  aria-label="Interview category"
                  value={config.category || ""}
                  onChange={(e) => edit("category", e.target.value || null)}
                >
                  <option value="">All categories</option>
                  {categories.map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
              </label>
              <label>
                Difficulty
                <select
                  aria-label="Interview difficulty"
                  value={config.difficulty || ""}
                  onChange={(e) => edit("difficulty", e.target.value || null)}
                >
                  <option value="">Mixed difficulty</option>
                  {["easy", "medium", "hard"].map((d) => (
                    <option key={d} value={d}>
                      {label(d)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Primary questions
                <input
                  aria-label="Primary questions"
                  required
                  type="number"
                  min={1}
                  max={20}
                  value={config.number_of_questions}
                  onChange={(e) =>
                    edit("number_of_questions", Number(e.target.value))
                  }
                />
              </label>
              <label>
                Question source
                <select
                  aria-label="Question source"
                  value={config.source}
                  onChange={(e) => edit("source", e.target.value)}
                >
                  {sources.map((s) => (
                    <option key={s} value={s}>
                      {label(s)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Question type
                <select
                  aria-label="Question type"
                  value={config.question_type || ""}
                  onChange={(e) =>
                    edit("question_type", e.target.value || null)
                  }
                >
                  <option value="">Match interview type</option>
                  {questionTypes.map((type) => (
                    <option key={type} value={type}>
                      {label(type)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label className="interview-check">
              <input
                type="checkbox"
                checked={config.allow_external_processing}
                onChange={(e) =>
                  edit("allow_external_processing", e.target.checked)
                }
              />
              Allow this session's answers and selected resume/JD evidence to be
              sent to the configured AI provider.
            </label>
            {!capability.enabled && (
              <p>
                AI evaluation is unavailable because no LLM provider is
                configured. Curated questions and answer saving remain
                available.
              </p>
            )}
            {previewError ? (
              <p role="alert">{previewError}</p>
            ) : (
              <p>
                {available === null
                  ? "Checking questions..."
                  : config.source === "ai_generated"
                    ? generationEnabled
                      ? "Ready for fresh AI questions"
                      : "AI question generation is unavailable"
                    : `${available} distinct questions available`}
              </p>
            )}
            <button
              className="primary"
              disabled={
                busy ||
                available === null ||
                available < config.number_of_questions ||
                (config.source === "ai_generated" &&
                  (!generationEnabled ||
                    (capability.external &&
                      !config.allow_external_processing))) ||
                !!previewError
              }
            >
              {busy
                ? config.source === "ai_generated"
                  ? "Generating questions..."
                  : "Starting..."
                : "Start interview"}
              <Play size={16} />
            </button>
          </form>
          <section className="interview-history" aria-label="Interview history">
            <h2>Recent interviews</h2>
            {!sessions.length ? (
              <p>No interview sessions yet.</p>
            ) : (
              sessions.map((s) => (
                <button
                  className="interview-history-row"
                  key={s.id}
                  onClick={() =>
                    void run(async () => {
                      await loadSession(s.id);
                    })
                  }
                >
                  <span>
                    <b>{label(s.configuration.interview_type)}</b>
                    <small>
                      {s.total_questions} questions ·{" "}
                      {new Date(s.created_at).toLocaleString()}
                    </small>
                  </span>
                  <span>{label(s.status)}</span>
                  <ArrowRight size={16} />
                </button>
              ))
            )}
          </section>
        </>
      ) : (
        <>
          <div className="interview-topbar">
            <button
              className="secondary"
              disabled={busy}
              onClick={() => void run(back)}
            >
              <ArrowLeft size={15} />
              All interviews
            </button>
            <span>
              {label(current.configuration.interview_type)} ·{" "}
              {label(current.status)}
            </span>
            {!closed && (
              <button
                className="secondary"
                disabled={busy || current.next_action === "wait"}
                onClick={() => {
                  if (
                    window.confirm(
                      "Abandon this interview? Submitted answers will be retained.",
                    )
                  )
                    void run(() => action("abandon"));
                }}
              >
                <Square size={14} />
                Abandon
              </button>
            )}
          </div>
          {closed && summary ? (
            <section
              className="interview-summary"
              aria-label="Interview summary"
            >
              {current.configuration.focus_id && (
                <a
                  className="text-action"
                  href={
                    "#weakness=" +
                    current.configuration.focus_id +
                    (current.configuration.target_id
                      ? "&target=" +
                        encodeURIComponent(current.configuration.target_id)
                      : "")
                  }
                >
                  Review learning signal <ArrowRight size={16} />
                </a>
              )}
              <h2>
                {current.status === "completed"
                  ? "Interview complete"
                  : "Interview abandoned"}
              </h2>
              <div className="interview-summary-counts">
                {[
                  [
                    "Primary answers",
                    `${summary.primary_answered} / ${summary.primary_questions}`,
                  ],
                  ["Follow-ups", summary.follow_ups],
                  ["Evaluated turns", summary.evaluations_completed],
                  ["Unscored answers", summary.unscored_answers],
                  [
                    "Average / 10",
                    summary.average_score?.toFixed(1) ?? "Not scored",
                  ],
                  [
                    "Primary average / 10",
                    summary.primary_average_score?.toFixed(1) ?? "Not scored",
                  ],
                ].map(([k, v]) => (
                  <div key={k}>
                    <strong>{v}</strong>
                    <span>{k}</span>
                  </div>
                ))}
              </div>
              <p>
                Model assessments of recorded answers, not an
                interview-readiness verdict. The overall average includes
                evaluated follow-ups; unscored answers are excluded.
              </p>
              <div className="feedback-columns">
                <div>
                  <h3>Demonstrated in answers</h3>
                  {summary.strong_areas.length ? (
                    <ul>
                      {summary.strong_areas.map((s) => (
                        <li key={s}>{s}</li>
                      ))}
                    </ul>
                  ) : (
                    <p>No assessed strengths recorded.</p>
                  )}
                </div>
                <div>
                  <h3>Suggested next practice</h3>
                  {summary.suggested_practice.length ? (
                    <ul>
                      {summary.suggested_practice.map((s) => (
                        <li key={s}>{s}</li>
                      ))}
                    </ul>
                  ) : (
                    <p>No evaluation-derived practice areas yet.</p>
                  )}
                </div>
                <div>
                  <h3>Repeated review topics</h3>
                  {summary.weak_areas.map((w) => (
                    <p key={w.skill + w.topic}>
                      {w.skill}: {w.topic} · {w.count} assessment
                      {w.count === 1 ? "" : "s"}
                    </p>
                  ))}
                </div>
              </div>
              <h3>Interview record</h3>
              {summary.turns.map((t) => (
                <details className="interview-record" key={t.id}>
                  <summary>
                    Question {t.primary_number}
                    {t.follow_up_depth
                      ? ` · Follow-up ${t.follow_up_depth}`
                      : ""}{" "}
                    · {t.evaluation?.score.toFixed(1) ?? "Unscored"}
                    {summary.review_turn_ids.includes(t.id)
                      ? " · Needs review"
                      : ""}
                  </summary>
                  <h3>{t.question_text}</h3>
                  <pre className="saved-answer">
                    {t.answer_text ?? "No answer submitted."}
                  </pre>
                  {t.evaluation && <Feedback value={t.evaluation} />}
                </details>
              ))}
            </section>
          ) : current.status === "not_started" ? (
            <button
              className="primary"
              disabled={busy}
              onClick={() => void run(() => action("start"))}
            >
              Begin saved interview
              <Play size={16} />
            </button>
          ) : (
            turn && (
              <>
                <div className="interview-progress">
                  <div>
                    <span>
                      Question {turn.primary_number} of{" "}
                      {current.total_questions}
                      {turn.follow_up_depth
                        ? ` · Follow-up ${turn.follow_up_depth} of 2`
                        : ""}
                    </span>
                    <span>
                      {current.resolved_primary_questions} primary questions
                      resolved
                    </span>
                  </div>
                  <progress
                    max={current.total_questions}
                    value={current.resolved_primary_questions}
                  />
                </div>
                <p className="interview-target">
                  {current.configuration.target_id
                    ? `Target comparison ${current.configuration.target_id.slice(0, 8)}`
                    : "General practice"}{" "}
                  · {turn.category} · {label(turn.difficulty)}
                </p>
                <h2
                  className="interview-question"
                  tabIndex={-1}
                  ref={questionRef}
                >
                  {turn.question_text}
                </h2>
                {current.status === "paused" ? (
                  <div className="interview-paused">
                    <p>Interview paused. Submitted answers are saved.</p>
                    <button
                      className="primary"
                      disabled={busy}
                      onClick={() => void run(() => action("resume"))}
                    >
                      Resume interview
                      <Play size={16} />
                    </button>
                  </div>
                ) : (
                  <>
                    {turn.answer_text === null ? (
                      <form
                        onSubmit={(e) => {
                          e.preventDefault();
                          void run(answer);
                        }}
                      >
                        <label className="answer-label">
                          Your answer
                          <textarea
                            aria-label="Your answer"
                            required
                            maxLength={20000}
                            rows={10}
                            value={draft}
                            disabled={busy}
                            onChange={(e) => setDraft(e.target.value)}
                          />
                        </label>
                        <div className="answer-footer">
                          <span>
                            {draft.length} / 20,000
                            {draft.length ? " · Unsaved draft" : ""}
                          </span>
                          <button
                            className="secondary"
                            type="button"
                            disabled={busy}
                            onClick={() => void run(() => action("pause"))}
                          >
                            <Pause size={15} />
                            Pause
                          </button>
                          <button
                            className="primary"
                            disabled={busy || !draft.trim()}
                          >
                            {busy ? "Saving answer..." : "Submit answer"}
                            <Send size={16} />
                          </button>
                        </div>
                      </form>
                    ) : (
                      <>
                        <div className="answer-saved">
                          <Check size={16} />
                          Answer saved
                        </div>
                        <pre className="saved-answer">{turn.answer_text}</pre>
                        {turn.evaluation ? (
                          <Feedback value={turn.evaluation} />
                        ) : (
                          <div className="evaluation-pending" role="status">
                            <p>
                              {busy || turn.evaluation_state === "evaluating"
                                ? "Evaluating saved answer..."
                                : turn.evaluation_error ||
                                  "Answer saved. Evaluation is pending."}
                            </p>
                            {turn.retryable && (
                              <>
                                {capability.external &&
                                  !current.configuration
                                    .allow_external_processing && (
                                    <label className="interview-check">
                                      <input
                                        type="checkbox"
                                        checked={consent}
                                        onChange={(e) =>
                                          setConsent(e.target.checked)
                                        }
                                      />
                                      Allow this answer and selected source
                                      evidence to be sent for evaluation.
                                    </label>
                                  )}
                                <button
                                  className="secondary"
                                  disabled={busy}
                                  onClick={() =>
                                    void run(() => evaluate(current))
                                  }
                                >
                                  <RefreshCw size={15} />
                                  {turn.evaluation_state === "pending"
                                    ? "Evaluate answer"
                                    : "Retry evaluation"}
                                </button>
                                {turn.evaluation_state !== "deferred" && (
                                  <button
                                    className="secondary"
                                    disabled={busy}
                                    onClick={() =>
                                      void run(() => action("defer_evaluation"))
                                    }
                                  >
                                    Continue unscored
                                    <ArrowRight size={15} />
                                  </button>
                                )}
                              </>
                            )}
                          </div>
                        )}
                        <div className="interview-actions">
                          <button
                            className="secondary"
                            disabled={busy || current.next_action === "wait"}
                            onClick={() => void run(() => action("pause"))}
                          >
                            <Pause size={15} />
                            Pause
                          </button>
                          {["follow_up", "next", "finish"].includes(
                            current.next_action,
                          ) && (
                            <button
                              className="primary"
                              disabled={busy}
                              onClick={() =>
                                void run(() =>
                                  action(
                                    current.next_action === "finish"
                                      ? "finish"
                                      : "next",
                                  ),
                                )
                              }
                            >
                              {current.next_action === "follow_up"
                                ? "Ask follow-up"
                                : current.next_action === "finish"
                                  ? "Finish interview"
                                  : "Next question"}
                              <ArrowRight size={16} />
                            </button>
                          )}
                        </div>
                      </>
                    )}
                  </>
                )}
              </>
            )
          )}
        </>
      )}
    </section>
  );
}
