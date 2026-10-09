import { useEffect, useState, useRef } from "react";
import {
  Upload,
  Plus,
  Trash2,
  Check,
  ArrowRight,
  FileText,
  ShieldCheck,
} from "lucide-react";
import { request } from "./api";
import "./analyzer.css";

type Kind = "resume" | "jd";
interface Evidence {
  document_id: string;
  start: number;
  end: number;
  quote: string;
}
interface Claim {
  id: string;
  category: string;
  value: string;
  origin: "extracted" | "user" | "ai_inferred";
  reviewed: boolean;
  uncertain: boolean;
  requirement: string;
  evidence: Evidence[];
}
interface Analysis {
  id: string;
  document_id: string;
  status: "draft" | "confirmed";
  revision: number;
  claims: Claim[];
  warnings: string[];
  method: string;
  created_at: string;
}
interface Bundle {
  document: { id: string; kind: Kind; filename: string; text: string };
  analyses: Analysis[];
  duplicate?: boolean;
}
interface DocList {
  id: string;
  kind: Kind;
  filename: string;
  created_at: string;
}
interface Match {
  focus_areas: string[];
  topic: string;
  status: string;
  priority: string;
  requirement: string;
  reason: string;
  priority_reason: string;
  preparation: string;
  resume_claims: Claim[];
  jd_claims: Claim[];
  source_mentions: Evidence[];
  absence_check: string | null;
  resume_document_id: string;
}
interface Target {
  id: string;
  resume_id: string;
  jd_id: string;
  result: { items: Match[]; notice: string };
}
const categories = [
  "name",
  "summary",
  "years_experience",
  "skills",
  "technologies",
  "cloud_platforms",
  "databases",
  "programming_languages",
  "projects",
  "work_experience",
  "responsibilities",
  "achievements",
  "certifications",
  "education",
  "experience_requirements",
  "domain_knowledge",
  "behavioral_requirements",
];
const label = (value: string) =>
  value.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
function EvidenceView({ claims }: { claims: Claim[] }) {
  return (
    <>
      {claims.map((c) => (
        <div className="source-claim" key={c.id}>
          <span>
            {label(c.origin)}
            {c.reviewed ? " · User confirmed" : ""}
          </span>
          {c.evidence.length ? (
            c.evidence.map((e, i) => (
              <blockquote key={i}>
                {e.quote}
                <cite>
                  Document {e.document_id}, characters {e.start}–{e.end}
                </cite>
              </blockquote>
            ))
          ) : (
            <p>User-supplied statement; no matching document excerpt.</p>
          )}
        </div>
      ))}
    </>
  );
}

export default function Analyzer() {
  const [kind, setKind] = useState<Kind>("resume"),
    [docs, setDocs] = useState<DocList[]>([]),
    [bundles, setBundles] = useState<Record<Kind, Bundle | null>>({
      resume: null,
      jd: null,
    });
  const [targets, setTargets] = useState<Target[]>([]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [paste, setPaste] = useState(""),
    [group, setGroup] = useState("all"),
    [dirty, setDirty] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const bundle = bundles[kind],
    analysis = bundle?.analyses[0];
  const resume = bundles.resume?.analyses[0],
    jd = bundles.jd?.analyses[0];
  const target = targets.find(
    (t) => t.resume_id === resume?.id && t.jd_id === jd?.id,
  );
  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Request failed. Retry after checking the local API.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function refreshDocs() {
    setDocs(await request<DocList[]>("/documents"));
  }
  async function load() {
    const [list, history] = await Promise.all([
      request<DocList[]>("/documents"),
      request<Target[]>("/targets"),
    ]);
    setDocs(list);
    setTargets(history);
    const next: Record<Kind, Bundle | null> = { resume: null, jd: null };
    for (const k of ["resume", "jd"] as Kind[]) {
      const found = list.find((d) => d.kind === k);
      if (found) next[k] = await request<Bundle>("/documents/" + found.id);
    }
    setBundles(next);
    setDirty(false);
  }
  useEffect(() => {
    void run(load);
  }, []);
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  function putBundle(next: Bundle) {
    setBundles((old) => ({ ...old, [next.document.kind]: next }));
    setDirty(false);
    setGroup("all");
  }
  function putAnalysis(next: Analysis) {
    if (!bundle) return;
    putBundle({
      ...bundle,
      analyses: [next, ...bundle.analyses.filter((a) => a.id !== next.id)],
    });
  }
  function modify(claims: Claim[]) {
    if (!analysis || !bundle) return;
    setBundles((old) => ({
      ...old,
      [kind]: {
        ...bundle,
        analyses: [{ ...analysis, claims }, ...bundle.analyses.slice(1)],
      },
    }));
    setDirty(true);
    setNotice("");
  }
  function updateClaim(id: string, patch: Partial<Claim>) {
    if (!analysis) return;
    modify(analysis.claims.map((c) => (c.id === id ? { ...c, ...patch } : c)));
  }
  async function upload(file: File) {
    if (file.size > 5 * 1024 * 1024) {
      setError("File exceeds the 5 MB limit.");
      return;
    }
    await run(async () => {
      const form = new FormData();
      form.append("kind", kind);
      form.append("file", file);
      const next = await request<Bundle>("/documents/upload", {
        method: "POST",
        body: form,
      });
      putBundle(next);
      await refreshDocs();
      setNotice(
        next.duplicate
          ? "Duplicate content found. Your existing reviews were preserved."
          : "Text extracted locally. Review the items and their evidence.",
      );
    });
    if (input.current) input.current.value = "";
  }
  async function save() {
    if (!analysis) return;
    const result = await request<Analysis>("/analyses/" + analysis.id, {
      method: "PUT",
      body: JSON.stringify({
        revision: analysis.revision,
        claims: analysis.claims,
      }),
    });
    putAnalysis(result);
    setNotice("Review saved.");
    return result;
  }
  async function confirm() {
    if (!analysis) return;
    const saved = dirty ? await save() : analysis;
    if (!saved) return;
    const confirmed = await request<Analysis>(`/analyses/${saved.id}/confirm`, {
      method: "POST",
      body: JSON.stringify({ revision: saved.revision }),
    });
    putAnalysis(confirmed);
    setNotice(
      `${kind === "resume" ? "Resume" : "Job description"} confirmed. This revision is now locked.`,
    );
  }
  const canCompare =
    resume?.status === "confirmed" && jd?.status === "confirmed" && !dirty;
  return (
    <div className="analyzer">
      <div className="analyzer-intro">
        <div>
          <h2>From evidence to preparation.</h2>
          <p>
            Review your resume and target role, then build a focused preparation
            map.
          </p>
        </div>
        <span className="method-label">LOCAL EXTRACTION · NO LLM REQUIRED</span>
      </div>
      <div className="analyzer-privacy">
        <ShieldCheck size={17} />
        <p>
          Use sanitized documents. Do not upload employer source code, customer
          data, credentials, internal architecture, or confidential information.
          Files are processed locally.
        </p>
      </div>
      <div className="workflow-steps">
        <span className={resume?.status === "confirmed" ? "complete" : ""}>
          01 Resume {resume?.status === "confirmed" && <Check size={14} />}
        </span>
        <span className={jd?.status === "confirmed" ? "complete" : ""}>
          02 Job description {jd?.status === "confirmed" && <Check size={14} />}
        </span>
        <span className={target ? "complete" : ""}>
          03 Preparation map {target && <Check size={14} />}
        </span>
      </div>
      {error && (
        <div role="alert" className="error">
          {error}
          <button disabled={busy || dirty} onClick={() => void run(load)}>
            Reload saved data
          </button>
        </div>
      )}
      {notice && (
        <p role="status" className="analyzer-notice">
          {notice}
        </p>
      )}
      <fieldset disabled={busy} className="analyzer-controls">
        <div className="analyzer-toolbar">
          <div className="document-tabs">
            {(["resume", "jd"] as Kind[]).map((k) => (
              <button
                key={k}
                type="button"
                aria-pressed={kind === k}
                disabled={dirty}
                className={kind === k ? "selected" : ""}
                onClick={() => {
                  setKind(k);
                  setGroup("all");
                  setPaste("");
                  setNotice("");
                }}
              >
                {k === "resume" ? "Resume" : "Job description"}
              </button>
            ))}
          </div>
          <label className="document-picker">
            Saved document
            <select
              disabled={dirty}
              aria-label="Saved document"
              value={bundle?.document.id || ""}
              onChange={(e) =>
                void run(async () =>
                  putBundle(
                    await request<Bundle>("/documents/" + e.target.value),
                  ),
                )
              }
            >
              <option value="" disabled>
                Select a document
              </option>
              {docs
                .filter((d) => d.kind === kind)
                .map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.filename} · {new Date(d.created_at).toLocaleDateString()}
                  </option>
                ))}
            </select>
          </label>
        </div>
        <div className="upload-row">
          <div>
            <FileText size={20} />
            <span>
              PDF, DOCX or TXT<small>Up to 5 MB · text-based PDFs</small>
            </span>
          </div>
          <button
            type="button"
            className="primary"
            disabled={dirty}
            onClick={() => input.current?.click()}
          >
            <Upload size={15} />
            Upload {kind === "resume" ? "resume" : "JD"}
          </button>
          <input
            ref={input}
            type="file"
            hidden
            accept=".pdf,.docx,.txt"
            aria-label={`Upload ${kind} file`}
            onChange={(e) => {
              if (e.target.files?.[0]) void upload(e.target.files[0]);
            }}
          />
        </div>
        <details className="paste-box">
          <summary>
            Paste {kind === "resume" ? "resume text" : "job description"}
          </summary>
          <label>
            Document text
            <textarea
              aria-label="Document text"
              value={paste}
              maxLength={100000}
              rows={6}
              onChange={(e) => setPaste(e.target.value)}
            />
          </label>
          <button
            type="button"
            className="secondary"
            disabled={!paste.trim() || dirty}
            onClick={() =>
              void run(async () => {
                const next = await request<Bundle>("/documents/text", {
                  method: "POST",
                  body: JSON.stringify({
                    kind,
                    text: paste,
                    filename: kind === "resume" ? "Pasted resume" : "Pasted JD",
                  }),
                });
                putBundle(next);
                setPaste("");
                await refreshDocs();
                setNotice(
                  next.duplicate
                    ? "Duplicate content found. Existing reviews preserved."
                    : "Extracted locally. Review before confirming.",
                );
              })
            }
          >
            Extract text
            <ArrowRight size={15} />
          </button>
        </details>
        {bundle && analysis && (
          <>
            <div className="review-heading">
              <div>
                <h3>Review extracted information</h3>
                <p>
                  {bundle.document.filename} ·{" "}
                  {analysis.status === "confirmed" ? "USER CONFIRMED" : "DRAFT"}
                  {dirty ? " · Unsaved changes" : ""}
                </p>
              </div>
              <label>
                Analysis revision
                <select
                  aria-label="Analysis revision"
                  disabled={dirty}
                  value={analysis.id}
                  onChange={(e) => {
                    const next = bundle.analyses.find(
                      (a) => a.id === e.target.value,
                    );
                    if (next) putAnalysis(next);
                  }}
                >
                  {bundle.analyses.map((a) => (
                    <option key={a.id} value={a.id}>
                      {new Date(a.created_at).toLocaleString()} · {a.status} ·{" "}
                      {a.method}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <details className="extraction-notes">
              <summary>Extraction notes ({analysis.warnings.length})</summary>
              {analysis.warnings.map((w, i) => (
                <p key={i}>{w}</p>
              ))}
            </details>
            <div className="review-toolbar">
              <label>
                Section
                <select
                  aria-label="Section"
                  value={group}
                  onChange={(e) => setGroup(e.target.value)}
                >
                  <option value="all">
                    All sections ({analysis.claims.length})
                  </option>
                  {categories.map((c) => (
                    <option key={c} value={c}>
                      {label(c)} (
                      {analysis.claims.filter((x) => x.category === c).length})
                    </option>
                  ))}
                </select>
              </label>
              {analysis.status === "draft" && (
                <button
                  className="secondary"
                  type="button"
                  onClick={() =>
                    modify([
                      ...analysis.claims,
                      {
                        id: crypto.randomUUID(),
                        category: group === "all" ? "skills" : group,
                        value: "",
                        origin: "user",
                        reviewed: true,
                        uncertain: false,
                        requirement: "unspecified",
                        evidence: [],
                      },
                    ])
                  }
                >
                  <Plus size={15} />
                  Add item
                </button>
              )}
            </div>
            <div className="claim-list">
              {analysis.claims
                .filter((c) => group === "all" || c.category === group)
                .map((claim, index) => (
                  <article className="claim-row" key={claim.id}>
                    <div className="claim-top">
                      <span className={"claim-badge " + claim.origin}>
                        {analysis.status === "confirmed"
                          ? "USER CONFIRMED"
                          : label(claim.origin).toUpperCase()}
                      </span>
                      <span className="claim-category">
                        {label(claim.category)}
                      </span>
                      {claim.uncertain && (
                        <span className="uncertain-label">Uncertain</span>
                      )}
                      {analysis.status === "draft" && (
                        <button
                          type="button"
                          className="icon-button"
                          title="Delete item"
                          aria-label={`Delete item ${index + 1}`}
                          onClick={() =>
                            modify(
                              analysis.claims.filter((c) => c.id !== claim.id),
                            )
                          }
                        >
                          <Trash2 size={14} />
                        </button>
                      )}
                    </div>
                    <label>
                      Value
                      <textarea
                        aria-label={`Value ${index + 1}`}
                        disabled={analysis.status === "confirmed"}
                        value={claim.value}
                        maxLength={3000}
                        rows={claim.value.length > 150 ? 3 : 2}
                        onChange={(e) =>
                          updateClaim(claim.id, {
                            value: e.target.value,
                            origin: "user",
                          })
                        }
                      />
                    </label>
                    {analysis.status === "draft" && (
                      <div className="claim-options">
                        <label>
                          Category
                          <select
                            aria-label={`Category ${index + 1}`}
                            value={claim.category}
                            onChange={(e) =>
                              updateClaim(claim.id, {
                                category: e.target.value,
                              })
                            }
                          >
                            {categories.map((c) => (
                              <option key={c} value={c}>
                                {label(c)}
                              </option>
                            ))}
                          </select>
                        </label>
                        {kind === "jd" && (
                          <label>
                            Importance
                            <select
                              aria-label={`Importance ${index + 1}`}
                              value={claim.requirement}
                              onChange={(e) =>
                                updateClaim(claim.id, {
                                  requirement: e.target.value,
                                })
                              }
                            >
                              {[
                                "unspecified",
                                "must_have",
                                "good_to_have",
                                "nice_to_have",
                              ].map((t) => (
                                <option value={t} key={t}>
                                  {label(t)}
                                </option>
                              ))}
                            </select>
                          </label>
                        )}
                        <label className="check-label">
                          <input
                            type="checkbox"
                            checked={claim.uncertain}
                            onChange={(e) =>
                              updateClaim(claim.id, {
                                uncertain: e.target.checked,
                              })
                            }
                          />
                          Uncertain
                        </label>
                        {claim.origin === "ai_inferred" && (
                          <label className="check-label">
                            <input
                              type="checkbox"
                              checked={claim.reviewed}
                              onChange={(e) =>
                                updateClaim(claim.id, {
                                  reviewed: e.target.checked,
                                })
                              }
                            />
                            I reviewed this inference
                          </label>
                        )}
                      </div>
                    )}
                    {kind === "jd" && analysis.status === "confirmed" && (
                      <p className="claim-category">
                        {label(claim.requirement)}
                      </p>
                    )}
                    <details className="claim-evidence">
                      <summary>
                        Source evidence{" "}
                        {claim.evidence.length
                          ? `(${claim.evidence.length})`
                          : "· User supplied"}
                      </summary>
                      <EvidenceView claims={[claim]} />
                    </details>
                  </article>
                ))}
            </div>
            {!analysis.claims.filter(
              (c) => group === "all" || c.category === group,
            ).length && (
              <p className="analyzer-empty">
                No items found in this section. Add accurate details or leave it
                unknown.
              </p>
            )}
            <div className="review-actions">
              {analysis.status === "draft" ? (
                <>
                  <button
                    type="button"
                    className="secondary"
                    disabled={
                      !dirty || analysis.claims.some((c) => !c.value.trim())
                    }
                    onClick={() =>
                      void run(async () => {
                        await save();
                      })
                    }
                  >
                    Save review
                  </button>
                  <button
                    type="button"
                    className="primary"
                    disabled={
                      !analysis.claims.length ||
                      analysis.claims.some((c) => !c.value.trim())
                    }
                    onClick={() => void run(confirm)}
                  >
                    <Check size={15} />
                    Confirm {kind === "resume" ? "resume" : "JD"}
                  </button>
                  {dirty && (
                    <button
                      type="button"
                      className="text-action"
                      onClick={() =>
                        void run(async () =>
                          putBundle(
                            await request<Bundle>(
                              "/documents/" + bundle.document.id,
                            ),
                          ),
                        )
                      }
                    >
                      Discard unsaved edits
                    </button>
                  )}
                </>
              ) : (
                <button
                  type="button"
                  className="secondary"
                  onClick={() =>
                    void run(async () =>
                      putAnalysis(
                        await request<Analysis>(
                          `/analyses/${analysis.id}/revision`,
                          { method: "POST" },
                        ),
                      ),
                    )
                  }
                >
                  Create editable revision
                </button>
              )}
            </div>
            <details className="source-document">
              <summary>Full extracted source</summary>
              <pre>{bundle.document.text}</pre>
            </details>
          </>
        )}
        <div className="compare-actions">
          <div>
            <h3>Build your preparation map</h3>
            <p>Both selected analyses must be confirmed.</p>
          </div>
          <button
            className="primary"
            type="button"
            disabled={!canCompare}
            onClick={() =>
              void run(async () => {
                const result = await request<Target>("/targets", {
                  method: "POST",
                  body: JSON.stringify({
                    resume_id: resume!.id,
                    jd_id: jd!.id,
                  }),
                });
                setTargets((old) => [
                  result,
                  ...old.filter((t) => t.id !== result.id),
                ]);
                setNotice(
                  "Comparison saved. Preparation priorities are based on confirmed evidence.",
                );
              })
            }
          >
            Compare resume & JD
            <ArrowRight size={15} />
          </button>
        </div>
      </fieldset>
      {busy && <p role="status">Processing locally...</p>}
      {target && (
        <section className="comparison" aria-label="Preparation map">
          <h2>Interview preparation map</h2>
          <p>{target.result.notice}</p>
          <div className="comparison-summary">
            {["strong", "partial", "missing", "needs_revision"].map((s) => (
              <span key={s}>
                <strong>
                  {target.result.items.filter((i) => i.status === s).length}
                </strong>
                {label(s)}
              </span>
            ))}
          </div>
          {!target.result.items.length && (
            <p>
              No comparable requirements were found. Add explicit JD
              requirements in a new reviewed revision.
            </p>
          )}
          {target.result.items.map((item, i) => (
            <article className="map-row" key={i}>
              <div className="map-title">
                <h3>{item.topic}</h3>
                <span>{label(item.status)}</span>
                <b>{item.priority.toUpperCase()} PRIORITY</b>
              </div>
              <p>{item.reason}</p>
              <p>
                <strong>Why this priority:</strong> {item.priority_reason}
              </p>
              <p>
                <strong>Preparation:</strong> {item.preparation}
              </p>
              <p>
                <strong>Suggested review topics:</strong>{" "}
                {item.focus_areas.join(" · ")}
              </p>
              <details open>
                <summary>Resume and JD evidence</summary>
                <h4>Resume</h4>
                {item.resume_claims.length ? (
                  <EvidenceView claims={item.resume_claims} />
                ) : (
                  <>
                    <p>
                      {item.absence_check ||
                        "No matching confirmed resume statement."}
                    </p>
                    <p>Resume document: {item.resume_document_id}</p>
                    {item.source_mentions.map((e, index) => (
                      <blockquote key={index}>
                        {e.quote}
                        <cite>
                          Source characters {e.start}–{e.end}
                        </cite>
                      </blockquote>
                    ))}
                  </>
                )}
                <h4>Job description</h4>
                <EvidenceView claims={item.jd_claims} />
              </details>
            </article>
          ))}
        </section>
      )}
    </div>
  );
}
