import { useEffect, useRef, useState } from "react";
import {
  Bookmark,
  ChevronLeft,
  ChevronRight,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import { request } from "./api";
import "./questions.css";

type Evidence = {
  document_id: string;
  start: number;
  end: number;
  quote: string;
};
type Link = {
  target_id: string;
  coverage: string;
  rationale: string;
  priority: number;
  absence_check: string | null;
  resume_claims: { evidence: Evidence[]; origin: string }[];
  jd_claims: { evidence: Evidence[]; origin: string }[];
  source_mentions: Evidence[];
};
type Question = {
  id: string;
  question_text: string;
  category: string;
  subcategory: string;
  skill: string;
  difficulty: string;
  question_type: string;
  tags: string[];
  expected_topics: string[];
  evaluation_focus: string;
  source: string;
  source_reference: {
    targets: Link[];
    path?: string;
    base_question_id?: string;
  };
  version: number;
  status: string;
  bookmarked: boolean;
  rationale: string;
};
type Stats = {
  total: number;
  curated: number;
  generated: number;
  saved: number;
};
type Target = {
  id: string;
  created_at: string;
  result: { items: { topic: string }[] };
};
const statuses = [
  "new",
  "in_progress",
  "practiced",
  "needs_review",
  "mastered",
];
const label = (value: string) =>
  value.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());

export default function QuestionBank({
  focusId = "",
  targetId = "",
  onRetest,
  onBack,
}: {
  focusId?: string;
  targetId?: string;
  onRetest?: (id: string) => void;
  onBack?: (id: string) => void;
}) {
  const retestKey = useRef(crypto.randomUUID());
  const [focusName, setFocusName] = useState("");
  useEffect(() => {
    if (focusId)
      void request<{ topic: string }>("/weaknesses/" + focusId)
        .then((v) => setFocusName(v.topic))
        .catch(() => setFocusName("Selected topic"));
  }, [focusId]);
  const [items, setItems] = useState<Question[]>([]),
    [total, setTotal] = useState(0);
  const [stats, setStats] = useState<Stats | null>(null),
    [metadata, setMetadata] = useState<Record<string, string[]>>({});
  const [filters, setFilters] = useState<Record<string, string>>({}),
    [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Question | null>(null),
    [error, setError] = useState("");
  const [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState("");
  const [refresh, setRefresh] = useState(0),
    [showGenerate, setShowGenerate] = useState(false);
  const [targets, setTargets] = useState<Target[]>([]),
    [target, setTarget] = useState("");
  const [generation, setGeneration] = useState<Record<string, string>>({
    category: "",
    difficulty: "",
    question_type: "",
  });
  const [count, setCount] = useState(5),
    [consent, setConsent] = useState(false),
    [enabled, setEnabled] = useState(false);
  const [available, setAvailable] = useState<number | null>(null);
  const sequence = useRef(0);
  const detailRef = useRef<HTMLElement>(null);
  useEffect(() => {
    detailRef.current?.focus();
  }, [selected?.id]);
  useEffect(() => {
    const current = ++sequence.current;
    setLoading(true);
    const timer = setTimeout(() => {
      const params = new URLSearchParams({
        ...filters,
        ...(focusId ? { focus_id: focusId, source: "curated" } : {}),
        offset: String(offset),
        limit: "12",
      });
      Promise.all([
        request<{ items: Question[]; total: number }>("/questions?" + params),
        request<Stats>("/questions/stats"),
        request<Record<string, string[]>>("/questions/metadata"),
      ])
        .then(([result, counts, options]) => {
          if (sequence.current !== current) return;
          setItems(result.items);
          setTotal(result.total);
          setStats(counts);
          setMetadata(options);
          setError("");
        })
        .catch((e) => {
          if (sequence.current === current) setError(e.message);
        })
        .finally(() => {
          if (sequence.current === current) setLoading(false);
        });
    }, 180);
    return () => {
      clearTimeout(timer);
      sequence.current++;
    };
  }, [filters, offset, refresh, focusId]);
  useEffect(() => {
    let active = true;
    Promise.all([
      request<Target[]>("/targets"),
      request<{ question_generation: { enabled: boolean } }>("/capabilities"),
    ])
      .then(([ts, cap]) => {
        if (active) {
          setTargets(ts);
          setTarget(ts[0]?.id || "");
          setEnabled(cap.question_generation.enabled);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    let active = true;
    setAvailable(null);
    if (!showGenerate || !target) return;
    request<{ available: number }>("/questions/generation-preview", {
      method: "POST",
      body: JSON.stringify({
        target_id: target,
        generation_mode: "draft",
        ...Object.fromEntries(
          Object.entries(generation).map(([key, value]) => [
            key,
            value || null,
          ]),
        ),
      }),
    })
      .then((result) => {
        if (active) setAvailable(result.available);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [showGenerate, target, generation]);
  function filter(key: string, value: string) {
    setFilters({ ...filters, [key]: value });
    setOffset(0);
  }
  async function update(q: Question, changes: Partial<Question>) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const saved = await request<Question>("/questions/" + q.id, {
        method: "PATCH",
        body: JSON.stringify({
          status: q.status,
          bookmarked: q.bookmarked,
          ...changes,
        }),
      });
      setSelected((current) => (current?.id === saved.id ? saved : current));
      setRefresh((v) => v + 1);
      setNotice("Question saved.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function generate() {
    if (busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await request<{
        items: Question[];
        created: number;
        reused: number;
      }>("/questions/generate", {
        method: "POST",
        body: JSON.stringify({
          target_id: target,
          generation_mode: "draft",
          ...Object.fromEntries(
            Object.entries(generation).map(([k, v]) => [k, v || null]),
          ),
          number_of_questions: count,
          allow_external_processing: consent,
        }),
      });
      setNotice(
        `${result.created} created; ${result.reused} existing questions reused.`,
      );
      setFilters({ source: "generated" });
      setOffset(0);
      setRefresh((v) => v + 1);
      setSelected(result.items[0] || null);
      setShowGenerate(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function bookmark(q: Question) {
    return (
      <button
        className="icon-button"
        disabled={busy}
        title={q.bookmarked ? "Remove bookmark" : "Bookmark question"}
        aria-label={q.bookmarked ? "Remove bookmark" : "Bookmark question"}
        aria-pressed={q.bookmarked}
        onClick={() => void update(q, { bookmarked: !q.bookmarked })}
      >
        <Bookmark size={18} fill={q.bookmarked ? "currentColor" : "none"} />
      </button>
    );
  }
  return (
    <section className="question-bank" aria-label="Question bank">
      {focusId && (
        <div className="bank-generation">
          <h2>Practice: {focusName}</h2>
          <button onClick={() => onBack?.(focusId)}>
            <ChevronLeft size={16} /> Topic evidence
          </button>
          <button
            className="primary"
            disabled={busy || !total}
            onClick={() => {
              setBusy(true);
              setError("");
              void request<{ interview: { id: string } }>(
                `/weaknesses/${focusId}/practice`,
                {
                  method: "POST",
                  body: JSON.stringify({
                    request_id: retestKey.current,
                    mode: "interview",
                    target_id: targetId || null,
                    number_of_questions: 1,
                  }),
                },
              )
                .then((v) => onRetest?.(v.interview.id))
                .catch((e) => setError(e.message))
                .finally(() => setBusy(false));
            }}
          >
            Start targeted interview
            <ChevronRight size={16} />
          </button>
        </div>
      )}
      <div className="bank-summary">
        {(["total", "curated", "generated", "saved"] as const).map((key) => (
          <div key={key}>
            <strong>{stats?.[key] ?? "-"}</strong>
            <span>{label(key)}</span>
          </div>
        ))}
        {!focusId && (
          <button
            className="primary"
            onClick={() => setShowGenerate(!showGenerate)}
          >
            <Sparkles size={16} /> Generate personalized questions
          </button>
        )}
      </div>
      {error && (
        <div role="alert" className="error">
          {error}
          <button onClick={() => setRefresh((v) => v + 1)}>Retry</button>
        </div>
      )}
      {notice && (
        <p role="status" className="bank-notice">
          {notice}
        </p>
      )}
      {showGenerate && (
        <form
          className="bank-generation"
          onSubmit={(e) => {
            e.preventDefault();
            void generate();
          }}
        >
          <h2>Personalized question set</h2>
          {!targets.length && (
            <p>
              No saved comparison. Confirm a resume and JD in Resume & JD, then
              compare them.
            </p>
          )}
          {!enabled && (
            <p>
              Live generation is disabled. Configure the LLM provider in the
              local environment to enable it.
            </p>
          )}
          <div className="bank-filters">
            <label>
              Target JD comparison
              <select
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                required
              >
                <option value="">Select comparison</option>
                {targets.map((t) => (
                  <option key={t.id} value={t.id}>
                    {new Date(t.created_at).toLocaleString()} ·{" "}
                    {t.result.items
                      .slice(0, 3)
                      .map((i) => i.topic)
                      .join(", ")}{" "}
                    · {t.id.slice(0, 8)}
                  </option>
                ))}
              </select>
            </label>
            {["category", "difficulty", "question_type"].map((key) => (
              <label key={key}>
                {label(key)}
                <select
                  aria-label={label(key)}
                  value={generation[key]}
                  onChange={(e) =>
                    setGeneration({ ...generation, [key]: e.target.value })
                  }
                >
                  <option value="">Any</option>
                  {metadata[key]?.map((v) => (
                    <option key={v} value={v}>
                      {label(v)}
                    </option>
                  ))}
                </select>
              </label>
            ))}
            <label>
              Number of questions
              <input
                type="number"
                min={1}
                max={20}
                required
                value={count}
                onChange={(e) => setCount(Number(e.target.value))}
              />
            </label>
          </div>
          <label className="bank-check">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
            />{" "}
            Allow selected resume/JD evidence to be sent to the configured AI
            provider.
          </label>
          <p>
            {available === null
              ? "Checking source evidence..."
              : available > 0
                ? "AI drafting ready"
                : "No matching skill in the selected target"}
          </p>
          <button
            className="primary"
            disabled={
              busy ||
              !target ||
              !enabled ||
              !consent ||
              available === null ||
              count > available
            }
          >
            {busy ? "Generating..." : "Generate set"}
            <Sparkles size={15} />
          </button>
        </form>
      )}
      <div className="bank-search">
        <Search size={18} />
        <input
          aria-label="Search questions"
          placeholder="Search questions, topics, tags..."
          value={filters.search || ""}
          onChange={(e) => filter("search", e.target.value)}
        />
      </div>
      <div className="bank-filters">
        {[
          "category",
          "skill",
          "difficulty",
          "question_type",
          "source",
          "status",
          "tag",
        ].map((key) => (
          <label key={key}>
            {label(key)}
            <select
              aria-label={"Filter " + label(key)}
              value={
                focusId && key === "source" ? "curated" : filters[key] || ""
              }
              disabled={!!focusId && key === "source"}
              onChange={(e) => filter(key, e.target.value)}
            >
              <option value="">All</option>
              {(key === "source"
                ? ["curated", "generated"]
                : key === "status"
                  ? statuses
                  : metadata[key === "tag" ? "tags" : key] || []
              ).map((v) => (
                <option key={v} value={v}>
                  {label(v)}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
      <div className="bank-listbar">
        <label className="bank-check">
          <input
            type="checkbox"
            checked={filters.saved === "true"}
            onChange={(e) => filter("saved", String(e.target.checked))}
          />{" "}
          Saved questions
        </label>
        <span>{total} results</span>
        <button
          className="text-action"
          onClick={() => {
            setFilters({});
            setOffset(0);
          }}
        >
          Clear filters
        </button>
      </div>
      <div className="bank-layout">
        <div className="bank-list" aria-busy={loading}>
          {loading ? (
            <p role="status">Loading questions...</p>
          ) : items.length === 0 ? (
            <p>No matching questions.</p>
          ) : (
            items.map((q) => (
              <article
                key={q.id}
                className={selected?.id === q.id ? "selected" : ""}
              >
                <div className="bank-rowhead">
                  <span>
                    {q.category} · {label(q.difficulty)} ·{" "}
                    {label(q.question_type)}
                  </span>
                  {bookmark(q)}
                </div>
                <button
                  className="question-open"
                  onClick={() => {
                    setSelected(q);
                  }}
                >
                  <h3>{q.question_text}</h3>
                </button>
                <div className="bank-rowfoot">
                  <span>
                    {label(q.source)} · v{q.version}
                  </span>
                  <span>{label(q.status)}</span>
                </div>
              </article>
            ))
          )}
          <div className="bank-pagination">
            <button
              className="icon-button"
              aria-label="Previous questions"
              title="Previous page"
              disabled={offset === 0 || loading}
              onClick={() => setOffset(Math.max(0, offset - 12))}
            >
              <ChevronLeft size={18} />
            </button>
            <span>
              {total ? Math.floor(offset / 12) + 1 : 0} /{" "}
              {Math.ceil(total / 12)}
            </span>
            <button
              className="icon-button"
              aria-label="Next questions"
              title="Next page"
              disabled={offset + 12 >= total || loading}
              onClick={() => setOffset(offset + 12)}
            >
              <ChevronRight size={18} />
            </button>
          </div>
        </div>
        {selected && (
          <section
            ref={detailRef}
            tabIndex={-1}
            className="bank-detail"
            aria-label="Question details"
          >
            <div className="bank-rowhead">
              <span>
                {label(selected.source)} · v{selected.version}
              </span>
              <button
                className="icon-button"
                aria-label="Close question details"
                title="Close details"
                onClick={() => setSelected(null)}
              >
                <X size={18} />
              </button>
            </div>
            <h2>{selected.question_text}</h2>
            <p>
              {selected.category} / {selected.subcategory} · {selected.skill} ·{" "}
              {label(selected.difficulty)} · {label(selected.question_type)}
            </p>
            <div className="bank-detail-actions">
              <label>
                Status
                <select
                  aria-label="Question status"
                  disabled={busy}
                  value={selected.status}
                  onChange={(e) =>
                    void update(selected, { status: e.target.value })
                  }
                >
                  {statuses.map((s) => (
                    <option key={s} value={s}>
                      {label(s)}
                    </option>
                  ))}
                </select>
              </label>
              {bookmark(selected)}
            </div>
            <h3>Expected topics</h3>
            <ul>
              {selected.expected_topics.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
            <h3>Evaluation focus</h3>
            <p>{selected.evaluation_focus}</p>
            <h3>Why this matters</h3>
            <p>{selected.rationale}</p>
            {selected.source_reference.targets.map((link) => (
              <div className="bank-evidence" key={link.target_id}>
                <p>{link.rationale}</p>
                <p>
                  Comparison {link.target_id} · Priority {link.priority}
                </p>
                {(["resume_claims", "jd_claims"] as const).map((side) => (
                  <div key={side}>
                    <h4>
                      {side === "resume_claims"
                        ? "Confirmed resume evidence"
                        : "JD requirement"}
                    </h4>
                    {link[side]
                      .flatMap((c) =>
                        c.evidence.map((e) => ({ ...e, origin: c.origin })),
                      )
                      .map((e, i) => (
                        <blockquote key={i}>
                          {e.quote}
                          <cite>
                            {label(e.origin)} · User reviewed · {e.document_id}{" "}
                            · characters {e.start}–{e.end}
                          </cite>
                        </blockquote>
                      ))}
                    {side === "resume_claims" &&
                      !link.resume_claims.length &&
                      link.source_mentions.map((e, i) => (
                        <blockquote key={i}>
                          {e.quote}
                          <cite>
                            Source mention requiring review · {e.document_id} ·
                            characters {e.start}–{e.end}
                          </cite>
                        </blockquote>
                      ))}
                  </div>
                ))}
                {link.absence_check && <p>{link.absence_check}</p>}
              </div>
            ))}
            <h3>Source</h3>
            <p>
              {selected.source_reference.path ||
                selected.source_reference.base_question_id}
            </p>
            <p>{selected.tags.join(" · ")}</p>
          </section>
        )}
      </div>
    </section>
  );
}
