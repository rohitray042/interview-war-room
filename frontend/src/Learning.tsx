import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  Search,
} from "lucide-react";
import { request } from "./api";
import "./learning.css";

type Quote = {
  quote: string;
  start: number;
  end: number;
  document_id?: string;
};
type Recommendation = {
  recommended: boolean;
  reason: string;
  available: number;
  limitation: string | null;
  questions: {
    id: string;
    question_text: string;
    difficulty: string;
    times_asked: number;
    status: string;
  }[];
};
type Topic = {
  id: string;
  skill: string;
  topic: string;
  category: string;
  description: string;
  status: string | null;
  practicing: boolean;
  revision: number;
  severity: string | null;
  severity_reason: string;
  confidence: string | null;
  confidence_reason: string;
  occurrence_count: number;
  independent_interviews: number;
  evidence_count: number;
  first_detected_at: string | null;
  last_detected_at: string | null;
  positive_count: number;
  strength_signal: string | null;
  improvement_signal: string;
  jd_relevant: boolean;
  jd_required: boolean;
  jd_evidence: { value: string; evidence: Quote[] }[];
  timeline: {
    session_id: string;
    assessment: string;
    at: string;
    evidence_count: number;
    follow_up_recovery: boolean;
  }[];
  recommendation: Recommendation;
};
type Evidence = {
  id: string;
  session_id: string;
  turn_id: string;
  evaluation_id: string;
  question_id: string;
  question: string;
  primary_number: number;
  follow_up_depth: number;
  assessment: string;
  observed_at: string;
  evidence: Quote[];
  absence_note: string | null;
};
type Detail = Topic & { evidence: Evidence[]; excluded_evaluations: number };
type List = {
  items: Topic[];
  stats: Record<string, number>;
  total: number;
  categories: string[];
  excluded_evaluations: number;
};
type Target = {
  id: string;
  created_at: string;
  result: { items: { topic: string }[] };
};
const label = (s: string | null) =>
  s
    ? s.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase())
    : "Not assessed";
const date = (s: string | null) =>
  s ? new Date(s).toLocaleString() : "No weak evidence";

export default function Learning({
  onOpen,
  onPractice,
}: {
  onOpen: (id: string) => void;
  onPractice: (id: string, target: string) => void;
}) {
  const initial = new URLSearchParams(location.hash.slice(1));
  const [selected, setSelected] = useState(initial.get("weakness") || "");
  const [target, setTarget] = useState(initial.get("target") || "");
  const [targets, setTargets] = useState<Target[]>([]);
  const [filters, setFilters] = useState({
    status: "active",
    category: "",
    severity: "",
    search: "",
  });
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<List | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [count, setCount] = useState(1);
  const key = useRef(crypto.randomUUID());
  const busyRef = useRef(false);
  useEffect(() => {
    void request<Target[]>("/targets")
      .then(setTargets)
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    const params = new URLSearchParams({
      ...filters,
      offset: String(offset),
      limit: "20",
    });
    if (target) params.set("target_id", target);
    const path = selected
      ? `/weaknesses/${selected}?${target ? "target_id=" + encodeURIComponent(target) : ""}`
      : "/weaknesses?" + params;
    const timer = setTimeout(() => {
      request<List | Detail>(path)
        .then((value) => {
          if (!active) return;
          if (selected) setDetail(value as Detail);
          else setData(value as List);
        })
        .catch((e) => {
          if (active) setError(e.message);
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    }, 120);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [selected, target, filters, offset, refresh]);
  function open(id: string, jd = target) {
    setSelected(id);
    setDetail(null);
    setCount(1);
    key.current = crypto.randomUUID();
    const params = new URLSearchParams(
      id ? { weakness: id } : { weaknesses: "all" },
    );
    if (jd) params.set("target", jd);
    history.replaceState(null, "", "#" + params);
  }
  async function mutate(task: () => Promise<void>) {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError("");
    try {
      await task();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }
  async function practice(mode: "study" | "interview") {
    if (!detail) return;
    await mutate(async () => {
      const result = await request<{ interview?: { id: string } }>(
        `/weaknesses/${detail.id}/practice`,
        {
          method: "POST",
          body: JSON.stringify({
            request_id: key.current,
            mode,
            target_id: target || null,
            number_of_questions: count,
          }),
        },
      );
      if (mode === "study") onPractice(detail.id, target);
      else if (result.interview) onOpen(result.interview.id);
    });
  }
  const warning = selected
    ? detail?.excluded_evaluations
    : data?.excluded_evaluations;
  return (
    <section className="learning" aria-label="Evidence-based weaknesses">
      <div className="learning-toolbar">
        {selected ? (
          <button onClick={() => open("")}>
            <ArrowLeft size={16} /> All topics
          </button>
        ) : (
          <h2>Learning signals</h2>
        )}
        <label>
          JD context
          <select
            aria-label="Learning target JD"
            value={target}
            onChange={(e) => {
              setTarget(e.target.value);
              setOffset(0);
              open(selected, e.target.value);
            }}
          >
            <option value="">General practice</option>
            {targets.map((t) => (
              <option key={t.id} value={t.id}>
                {t.result.items
                  .slice(0, 2)
                  .map((i) => i.topic)
                  .join(", ")}{" "}
                · {t.id.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>
        <button
          className="icon-button"
          title="Refresh learning evidence"
          aria-label="Refresh learning evidence"
          onClick={() => setRefresh((n) => n + 1)}
        >
          <RefreshCw size={17} />
        </button>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!!warning && (
        <p role="alert">
          {warning} stored evaluations failed evidence validation and were
          excluded.
        </p>
      )}
      {!selected && (
        <>
          <div className="learning-counts">
            {Object.entries(data?.stats || {}).map(([name, value]) => (
              <span key={name}>
                <strong>{value}</strong> {label(name)}
              </span>
            ))}
          </div>
          <div
            className="learning-tabs"
            role="group"
            aria-label="Learning views"
          >
            {[
              "all",
              "active",
              "improving",
              "resolved",
              "strengths",
              "jd_relevant",
            ].map((s) => (
              <button
                key={s}
                aria-pressed={filters.status === s}
                onClick={() => {
                  setFilters({ ...filters, status: s });
                  setOffset(0);
                }}
              >
                {label(s)}
              </button>
            ))}
          </div>
          <div className="learning-filters">
            <label className="learning-search">
              <Search size={16} />
              <input
                aria-label="Search learning topics"
                placeholder="Search skills and topics"
                value={filters.search}
                onChange={(e) => {
                  setFilters({ ...filters, search: e.target.value });
                  setOffset(0);
                }}
              />
            </label>
            <label>
              Category
              <select
                aria-label="Learning category"
                value={filters.category}
                onChange={(e) => {
                  setFilters({ ...filters, category: e.target.value });
                  setOffset(0);
                }}
              >
                <option value="">All categories</option>
                {data?.categories.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
            <label>
              Severity
              <select
                aria-label="Learning severity"
                value={filters.severity}
                onChange={(e) => {
                  setFilters({ ...filters, severity: e.target.value });
                  setOffset(0);
                }}
              >
                <option value="">All severities</option>
                {["low", "medium", "high"].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </label>
          </div>
        </>
      )}
      {loading ? (
        <p role="status">Loading learning evidence...</p>
      ) : selected && detail ? (
        <>
          <header className="learning-heading">
            <span>
              {detail.category} / {detail.skill}
            </span>
            <h2>{detail.topic}</h2>
            <p>{detail.description}</p>
          </header>
          <div className="learning-facts">
            <div>
              <span>Status</span>
              <strong>
                {detail.status
                  ? label(detail.status)
                  : "Positive evidence only"}
              </strong>
            </div>
            <div>
              <span>Severity</span>
              <strong>{label(detail.severity)}</strong>
            </div>
            <div>
              <span>Confidence</span>
              <strong>{label(detail.confidence)}</strong>
            </div>
            <div>
              <span>Weak assessments</span>
              <strong>{detail.occurrence_count}</strong>
            </div>
            <div>
              <span>Independent interviews</span>
              <strong>{detail.independent_interviews}</strong>
            </div>
            <div>
              <span>Evidence points</span>
              <strong>{detail.evidence_count}</strong>
            </div>
          </div>
          {detail.status && (
            <>
              <p>{detail.severity_reason}</p>
              <p>{detail.confidence_reason}</p>
            </>
          )}
          <p>
            <strong>{detail.improvement_signal}</strong>
          </p>
          {detail.strength_signal && (
            <p>
              {label(detail.strength_signal)} positive signal ·{" "}
              {detail.positive_count} supported answers. Not a mastery claim.
            </p>
          )}
          <p>
            First detected: {date(detail.first_detected_at)}
            <br />
            Last detected: {date(detail.last_detected_at)}
          </p>
          {detail.status && detail.status !== "resolved" && (
            <button
              disabled={busy}
              onClick={() =>
                void mutate(async () => {
                  await request(`/weaknesses/${detail.id}/status`, {
                    method: "PATCH",
                    body: JSON.stringify({
                      status: detail.practicing ? "detected" : "practicing",
                      revision: detail.revision,
                    }),
                  });
                  setRefresh((n) => n + 1);
                })
              }
            >
              <BookOpen size={16} />
              {detail.practicing ? "Stop practice tracking" : "Mark practicing"}
            </button>
          )}
          <section className="learning-section" aria-label="JD relevance">
            <h3>JD relevance</h3>
            <p>
              {detail.jd_required
                ? "Required by the selected JD"
                : detail.jd_relevant
                  ? "Related to the selected JD"
                  : "General topic; no matching selected JD requirement"}
            </p>
            {detail.jd_evidence
              .flatMap((c) => c.evidence)
              .map((q, i) => (
                <blockquote key={i}>
                  {q.quote}
                  <cite>
                    JD source {q.document_id} · characters {q.start}–{q.end}
                  </cite>
                </blockquote>
              ))}
          </section>
          <section
            className="learning-section"
            aria-label="Recommended practice"
          >
            <h3>Recommended practice</h3>
            <p>{detail.recommendation.reason}</p>
            <p>
              {detail.recommendation.available} exact-topic questions available.
            </p>
            {detail.recommendation.limitation && (
              <p>{detail.recommendation.limitation}</p>
            )}
            <div className="learning-actions">
              <button
                disabled={busy || !detail.recommendation.available}
                onClick={() => void practice("study")}
              >
                <BookOpen size={16} />
                Practice This
              </button>
              <label>
                Questions
                <input
                  aria-label="Targeted question count"
                  type="number"
                  min={1}
                  max={Math.min(5, detail.recommendation.available)}
                  value={count}
                  onChange={(e) => {
                    setCount(Number(e.target.value));
                    key.current = crypto.randomUUID();
                  }}
                />
              </label>
              <button
                className="primary"
                disabled={
                  busy ||
                  !detail.recommendation.available ||
                  count < 1 ||
                  count > Math.min(5, detail.recommendation.available)
                }
                onClick={() => void practice("interview")}
              >
                Start targeted interview
                <ArrowRight size={16} />
              </button>
            </div>
          </section>
          <section className="learning-section" aria-label="Performance trend">
            <h3>Performance trend</h3>
            <ol className="learning-timeline">
              {detail.timeline.map((point) => (
                <li key={point.session_id}>
                  <strong>{label(point.assessment)}</strong> · {date(point.at)}
                  <br />
                  <button
                    className="text-action"
                    onClick={() => onOpen(point.session_id)}
                  >
                    Interview {point.session_id.slice(0, 8)}
                    <ArrowRight size={14} />
                  </button>
                  <span>
                    {point.evidence_count} evidence points
                    {point.follow_up_recovery
                      ? " · Follow-up recovery, not independent confirmation"
                      : ""}
                  </span>
                </li>
              ))}
            </ol>
          </section>
          <section className="learning-section" aria-label="Learning evidence">
            <h3>Supporting interview evidence</h3>
            {detail.evidence.map((e) => (
              <article className="learning-evidence" key={e.id}>
                <p>
                  {date(e.observed_at)} · {label(e.assessment)} · Question{" "}
                  {e.primary_number}
                  {e.follow_up_depth ? ` · Follow-up ${e.follow_up_depth}` : ""}
                </p>
                <h4>{e.question}</h4>
                {e.evidence.map((q, i) => (
                  <blockquote key={i}>
                    {q.quote}
                    <cite>
                      Answer characters {q.start}–{q.end}
                    </cite>
                  </blockquote>
                ))}
                {e.absence_note && <p>{e.absence_note}</p>}
                <button
                  className="text-action"
                  onClick={() => onOpen(e.session_id)}
                >
                  Open interview record
                  <ArrowRight size={14} />
                </button>
                <details>
                  <summary>Evidence references</summary>
                  <p>
                    Question: {e.question_id}
                    <br />
                    Turn: {e.turn_id}
                    <br />
                    Evaluation: {e.evaluation_id}
                  </p>
                </details>
              </article>
            ))}
          </section>
        </>
      ) : !selected && data ? (
        <>
          {!data.items.length ? (
            <p>No evaluation-derived review topics yet for these filters.</p>
          ) : (
            <div className="learning-list">
              {data.items.map((row) => (
                <article key={row.id}>
                  <div>
                    <span>
                      {row.skill} · {row.category}
                    </span>
                    <h3>
                      <button
                        className="text-action"
                        aria-label={`Open topic ${row.topic}`}
                        onClick={() => open(row.id)}
                      >
                        {row.topic}
                        <ArrowRight size={16} />
                      </button>
                    </h3>
                    <p>
                      {label(row.status || row.strength_signal)} ·{" "}
                      {row.occurrence_count} assessments ·{" "}
                      {row.independent_interviews} independent interviews
                    </p>
                  </div>
                  <div>
                    <p>
                      {row.severity
                        ? `${label(row.severity)} severity · ${label(row.confidence)} confidence`
                        : "Positive evidence"}
                      {row.jd_relevant ? " · JD relevant" : ""}
                    </p>
                    <p>{row.recommendation.reason}</p>
                    <small>{row.improvement_signal}</small>
                  </div>
                </article>
              ))}
            </div>
          )}
          <div className="learning-pagination">
            <button
              className="icon-button"
              aria-label="Previous topics"
              title="Previous topics"
              disabled={!offset}
              onClick={() => setOffset(Math.max(0, offset - 20))}
            >
              <ChevronLeft size={18} />
            </button>
            <span>
              {data.total} topics · Page {Math.floor(offset / 20) + 1}
            </span>
            <button
              className="icon-button"
              aria-label="Next topics"
              title="Next topics"
              disabled={offset + 20 >= data.total}
              onClick={() => setOffset(offset + 20)}
            >
              <ChevronRight size={18} />
            </button>
          </div>
        </>
      ) : null}
    </section>
  );
}
