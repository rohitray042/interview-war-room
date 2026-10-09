import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  ChevronRight,
  FileText,
  LayoutDashboard,
  LockKeyhole,
  Mic,
  Moon,
  PanelTop,
  Settings,
  ShieldCheck,
  Sun,
  Target,
  TrendingUp,
} from "lucide-react";
import { request, type Profile, type Manifest } from "./api";
import "./style.css";
import Analyzer from "./Analyzer";
import QuestionBank from "./QuestionBank";
import MockInterview from "./MockInterview";
import Learning from "./Learning";
import AIStatus from "./AIStatus";
import DevicePrivacy from "./DevicePrivacy";

const navigation = [
  { name: "Overview", icon: LayoutDashboard },
  { name: "Resume & JD", icon: FileText },
  { name: "Question bank", icon: BookOpen },
  { name: "Mock interview", icon: Mic, later: false },
  { name: "Weaknesses", icon: Target, later: false },
];
const skills = [
  "Java",
  "Apache Spark",
  "Snowflake",
  "GCP",
  "SQL",
  "Cassandra",
  "ETL",
  "CI/CD",
];
function App() {
  const [routeHash, setRouteHash] = useState(location.hash);
  const [workspace, setWorkspace] = useState<{
    data: "user" | "fixtures" | "persisted-copy";
    simulated_ai: boolean;
  } | null>(null);
  const [page, setPage] = useState(() =>
    location.hash.startsWith("#interview=")
      ? "Mock interview"
      : location.hash.startsWith("#weak")
        ? "Weaknesses"
        : location.hash.startsWith("#practice=")
          ? "Question bank"
          : "Overview",
  );
  useEffect(() => {
    const navigate = () => {
      setRouteHash(location.hash);
      setPage(
        location.hash.startsWith("#interview=")
          ? "Mock interview"
          : location.hash.startsWith("#weak")
            ? "Weaknesses"
            : location.hash.startsWith("#practice=")
              ? "Question bank"
              : "Overview",
      );
    };
    window.addEventListener("hashchange", navigate);
    return () => window.removeEventListener("hashchange", navigate);
  }, []);
  const [counts, setCounts] = useState<{
    answers: number;
    completed_sessions: number;
    topics_assessed: number;
  } | null>(null);
  useEffect(() => {
    if (page === "Overview")
      void request<{
        answers: number;
        completed_sessions: number;
        topics_assessed: number;
      }>("/interviews/stats")
        .then(setCounts)
        .catch(() => setCounts(null));
  }, [page]);
  const [profile, setProfile] = useState<Profile | null>(null),
    [manifest, setManifest] = useState<Manifest | null>(null);
  const [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [saving, setSaving] = useState(false),
    [saved, setSaved] = useState(false);
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem("war-room-theme") === "dark"
        ? "dark"
        : "light";
    } catch {
      return "light";
    }
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("war-room-theme", theme);
    } catch {
      /* Theme still works if storage is disabled. */
    }
  }, [theme]);
  async function load() {
    setLoading(true);
    setError("");
    try {
      const [p, m, c] = await Promise.all([
        request<Profile>("/profile"),
        request<Manifest>("/content/manifest"),
        request<{ workspace: NonNullable<typeof workspace> }>("/capabilities"),
      ]);
      setProfile(p);
      setManifest(m);
      setWorkspace(c.workspace);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Could not connect to the local API.",
      );
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void load();
  }, []);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!profile || saving) return;
    setSaving(true);
    setSaved(false);
    setError("");
    const payload = {
      name: profile.name,
      background: profile.background,
      target_role: profile.target_role,
      skills: profile.skills.map((s) => s.trim()).filter(Boolean),
      learning_skills: profile.learning_skills
        .map((s) => s.trim())
        .filter(Boolean),
      daily_study_minutes: profile.daily_study_minutes,
    };
    try {
      setProfile(
        await request<Profile>("/profile", {
          method: "PUT",
          body: JSON.stringify(payload),
        }),
      );
      setSaved(true);
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Save failed. Your edits are still here.",
      );
    } finally {
      setSaving(false);
    }
  }
  function edit<K extends keyof Profile>(key: K, value: Profile[K]) {
    if (profile) setProfile({ ...profile, [key]: value });
    setSaved(false);
  }
  return (
    <div className="shell">
      <aside className="sidebar">
        <a href="#" className="brand" onClick={() => setPage("Overview")}>
          <span className="brand-mark">
            <PanelTop size={22} />
          </span>
          <span>
            INTERVIEW
            <br />
            <b>WAR ROOM</b>
          </span>
        </a>
        <div className="workspace">PERSONAL WORKSPACE</div>
        <nav>
          {navigation.map(({ name, icon: Icon, later }) => (
            <button
              key={name}
              title={later ? `${name} · upcoming milestone` : name}
              aria-label={name}
              disabled={later}
              className={page === name ? "active" : ""}
              onClick={() => {
                if (
                  name !== "Mock interview" &&
                  location.hash.startsWith("#interview=")
                )
                  history.replaceState(
                    null,
                    "",
                    location.pathname + location.search,
                  );
                setPage(name);
              }}
            >
              <Icon size={18} />
              <span>{name}</span>
              {later && <LockKeyhole size={12} className="nav-lock" />}
            </button>
          ))}
        </nav>
        <div className="nav-bottom">
          <div className="local-note">
            <ShieldCheck size={18} />
            <div>
              Local by design<small>Your preparation. Your device.</small>
            </div>
          </div>
          <button
            aria-label="Profile & settings"
            title="Profile & settings"
            className={page === "Profile" ? "active" : ""}
            onClick={() => {
              setPage("Profile");
              setSaved(false);
            }}
          >
            <Settings size={18} />
            Profile & settings
          </button>
          <div className="account">
            <span className="avatar">{profile?.name?.charAt(0) || "?"}</span>
            <div>
              {profile?.name || "Personal workspace"}
              <small>Data engineering track</small>
            </div>
          </div>
        </div>
      </aside>
      <main>
        <header>
          <div className="breadcrumbs">
            Workspace <ChevronRight size={14} />
            <span>{page}</span>
          </div>
          <div className="header-actions">
            <AIStatus />
            <span className={"connection " + (error ? "offline" : "")}>
              <i />
              {loading
                ? "Connecting"
                : error
                  ? "Connection needs attention"
                  : workspace?.data !== "user" && workspace
                    ? "Test workspace"
                    : "Local workspace"}
            </span>
            <button
              className="icon-button"
              aria-label={
                theme === "light" ? "Use dark theme" : "Use light theme"
              }
              title="Change theme"
              onClick={() => setTheme(theme === "light" ? "dark" : "light")}
            >
              {theme === "light" ? <Moon size={17} /> : <Sun size={17} />}
            </button>
          </div>
        </header>
        <div className="content">
          {workspace && workspace.data !== "user" && (
            <p
              role="note"
              aria-label="Workspace data provenance"
              className="verification-notice"
            >
              {workspace.data === "persisted-copy"
                ? "Verification copy of saved user data. Original workspace unchanged."
                : "Test fixtures. Not your personal workspace."}
              {workspace.simulated_ai
                ? " Simulated AI evaluations; not genuine performance results."
                : " AI evaluation disabled."}
            </p>
          )}
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                DATA ENGINEERING / INTERVIEW PREPARATION
              </div>
              <h1>
                {page === "Profile"
                  ? "Make this room yours."
                  : page === "Resume & JD"
                    ? "Resume & JD analyzer."
                    : page === "Question bank"
                      ? "Question bank."
                      : page === "Mock interview"
                        ? "Mock interview."
                        : page === "Weaknesses"
                          ? "Evidence-led practice."
                          : profile?.name
                            ? `Your next chapter, ${profile.name.split(" ")[0]}.`
                            : "Your next chapter starts here."}
              </h1>
              <p>
                {page === "Profile"
                  ? "Set the direction for your preparation."
                  : "A focused space to turn experience into interview confidence."}
              </p>
            </div>
            <span className="milestone">
              ADAPTIVE PRACTICE <b>05</b>
            </span>
          </div>
          {error && (
            <div className="error" role="alert">
              {error}
              <button onClick={() => void load()}>Reconnect</button>
            </div>
          )}
          <DevicePrivacy controls={page === "Profile"} />
          {loading ? (
            <div className="loading" role="status">
              Connecting to your workspace...
            </div>
          ) : page === "Resume & JD" ? (
            <Analyzer />
          ) : page === "Question bank" ? (
            <QuestionBank
              key={routeHash}
              focusId={
                new URLSearchParams(location.hash.slice(1)).get("practice") ||
                ""
              }
              targetId={
                new URLSearchParams(location.hash.slice(1)).get("target") || ""
              }
              onRetest={(id) => {
                history.replaceState(null, "", "#interview=" + id);
                setPage("Mock interview");
              }}
              onBack={(id) => {
                const target = new URLSearchParams(location.hash.slice(1)).get(
                  "target",
                );
                history.replaceState(
                  null,
                  "",
                  "#weakness=" +
                    id +
                    (target ? "&target=" + encodeURIComponent(target) : ""),
                );
                setPage("Weaknesses");
              }}
            />
          ) : page === "Mock interview" ? (
            <MockInterview key={routeHash} />
          ) : page === "Weaknesses" ? (
            <Learning
              key={routeHash}
              onOpen={(id) => {
                history.replaceState(null, "", "#interview=" + id);
                setPage("Mock interview");
              }}
              onPractice={(id, target) => {
                const params = new URLSearchParams({ practice: id });
                if (target) params.set("target", target);
                history.replaceState(null, "", "#" + params);
                setPage("Question bank");
              }}
            />
          ) : page === "Profile" && profile ? (
            <form className="profile-form" onSubmit={save}>
              <div className="section-heading">
                <h2>Preparation profile</h2>
                <span>Stored on this device</span>
              </div>
              <div className="form-grid">
                <label>
                  Name
                  <input
                    maxLength={100}
                    value={profile.name}
                    onChange={(e) => edit("name", e.target.value)}
                  />
                </label>
                <label>
                  Target role
                  <input
                    required
                    maxLength={120}
                    value={profile.target_role}
                    onChange={(e) => edit("target_role", e.target.value)}
                  />
                </label>
                <label className="wide">
                  Background
                  <textarea
                    maxLength={4000}
                    rows={4}
                    value={profile.background}
                    onChange={(e) => edit("background", e.target.value)}
                  />
                </label>
                <label className="wide">
                  Current skills
                  <input
                    aria-label="Current skills"
                    aria-describedby="skills-hint"
                    defaultValue={profile.skills.join(", ")}
                    onChange={(e) =>
                      edit(
                        "skills",
                        e.target.value.split(",").map((s) => s.trim()),
                      )
                    }
                  />
                  <small id="skills-hint">Separate skills with commas.</small>
                </label>
                <label className="wide">
                  Currently learning
                  <input
                    defaultValue={profile.learning_skills.join(", ")}
                    onChange={(e) =>
                      edit(
                        "learning_skills",
                        e.target.value.split(",").map((s) => s.trim()),
                      )
                    }
                  />
                </label>
                <label>
                  Daily study time (minutes)
                  <input
                    type="number"
                    min={5}
                    max={480}
                    required
                    value={profile.daily_study_minutes}
                    onChange={(e) =>
                      edit("daily_study_minutes", Number(e.target.value))
                    }
                  />
                </label>
              </div>
              <div className="form-footer">
                <button className="primary" disabled={saving}>
                  {saving ? "Saving..." : "Save profile"}
                  <Check size={16} />
                </button>
                {saved && <span role="status">Profile saved</span>}
              </div>
              <div className="privacy-warning">
                <ShieldCheck size={19} />
                <p>
                  Use sanitized information. Do not enter employer source code,
                  customer data, credentials, internal architecture, or
                  confidential documents. AI processing requires provider
                  configuration and explicit consent.
                </p>
              </div>
            </form>
          ) : (
            <>
              <section className="intro-band">
                <div className="intro-copy">
                  <span className="small-label">
                    YOUR PREPARATION, WITH PURPOSE
                  </span>
                  <h2>
                    Less guessing.
                    <br />
                    More deliberate practice.
                  </h2>
                  <p>
                    Bring your experience. Build your confidence.
                    <br />
                    Measure the progress that matters.
                  </p>
                  <button
                    className="primary"
                    onClick={() => setPage("Profile")}
                  >
                    {profile?.name
                      ? "Edit preparation profile"
                      : "Set up your profile"}
                    <ArrowRight size={17} />
                  </button>
                </div>
                <div
                  className="journey-art"
                  role="img"
                  aria-label="Preparation path: experience, practice, feedback, progress"
                >
                  <div className="art-grid" />
                  <div className="art-row">
                    <span>01</span>
                    <FileText size={19} />
                    <b>YOUR EXPERIENCE</b>
                    <Check size={15} />
                  </div>
                  <div className="art-connector" />
                  <div className="art-row">
                    <span>02</span>
                    <Target size={19} />
                    <b>FOCUSED PRACTICE</b>
                    <ArrowUpRight size={15} />
                  </div>
                  <div className="art-connector" />
                  <div className="art-row">
                    <span>03</span>
                    <TrendingUp size={19} />
                    <b>MEASURABLE GROWTH</b>
                    <ArrowUpRight size={15} />
                  </div>
                  <span className="art-caption">
                    One intentional step at a time.
                  </span>
                </div>
              </section>
              <section className="metrics" aria-label="Preparation metrics">
                {[
                  [
                    "Questions attempted",
                    "Persisted answers, including follow-ups",
                    counts?.answers ?? "—",
                  ],
                  ["Interview readiness", "Not assessed yet", "—"],
                  [
                    "Topics assessed",
                    "Skills with recorded answer evaluations",
                    counts?.topics_assessed ?? "—",
                  ],
                  [
                    "Sessions completed",
                    "Completed mock interviews",
                    counts?.completed_sessions ?? "—",
                  ],
                ].map(([label, note, value]) => (
                  <div className="metric" key={label}>
                    <span>{label}</span>
                    <strong>{value}</strong>
                    <small>{note}</small>
                  </div>
                ))}
              </section>
              <div className="lower-grid">
                <section>
                  <div className="section-heading">
                    <h2>Your preparation track</h2>
                    <span>START WITH WHAT YOU KNOW</span>
                  </div>
                  <div className="track-list">
                    {[
                      {
                        icon: FileText,
                        title: "Connect your experience",
                        detail: "Resume evidence and target-role requirements.",
                        phase: "02",
                        done: false,
                      },
                      {
                        icon: BookOpen,
                        title: "Build your question bank",
                        detail:
                          "Questions grounded in your work and skill gaps.",
                        phase: "03",
                        done: false,
                      },
                      {
                        icon: Mic,
                        title: "Practise with intent",
                        detail:
                          "Focused interviews and structured answer feedback.",
                        phase: "04–05",
                        done: false,
                      },
                    ].map(({ icon: Icon, title, detail, phase }) => (
                      <div className="track" key={title}>
                        <span className="track-icon">
                          <Icon size={20} />
                        </span>
                        <div>
                          <h3>{title}</h3>
                          <p>{detail}</p>
                        </div>
                        <span className="phase">MILESTONE {phase}</span>
                      </div>
                    ))}
                  </div>
                  <div className="empty-history">
                    <div>
                      <TrendingUp size={20} />
                      <h3>
                        {counts?.answers
                          ? "Your practice record"
                          : "A fresh starting point"}
                      </h3>
                    </div>
                    <p>
                      {counts?.answers
                        ? "Review your mock interviews for recorded answers and feedback. No readiness score has been assigned."
                        : "Progress will appear after evaluated practice sessions. No scores have been assigned."}
                    </p>
                  </div>
                </section>
                <section className="focus-section">
                  <div className="section-heading">
                    <h2>Technical focus</h2>
                    <button
                      className="icon-button"
                      title="Edit profile"
                      aria-label="Edit technical focus"
                      onClick={() => setPage("Profile")}
                    >
                      <ArrowUpRight size={17} />
                    </button>
                  </div>
                  <div className="skill-list">
                    {(profile?.skills.filter(Boolean).length
                      ? profile.skills
                      : skills
                    ).map((skill, i) => (
                      <span key={`${skill}-${i}`}>{skill}</span>
                    ))}
                  </div>
                  <p className="caption">
                    {profile?.skills.filter(Boolean).length
                      ? "From your preparation profile"
                      : "Suggested topics · customize in your profile"}
                  </p>
                  <div className="content-status">
                    <span className="small-label">FOUNDATION CHECK</span>
                    <div>
                      <Check size={15} />
                      {profile
                        ? "SQLite workspace connected"
                        : "SQLite connection unavailable"}
                    </div>
                    <div>
                      <Check size={15} />
                      {manifest?.questions.length ?? 0} sample questions loaded
                    </div>
                    <div>
                      <Check size={15} />
                      {manifest?.rubrics.length ?? 0} versioned scoring rubric
                    </div>
                    <div>
                      <LockKeyhole size={15} />
                      Analyzer runs locally
                    </div>
                  </div>
                </section>
              </div>
            </>
          )}
          <footer>
            <span>
              <ShieldCheck size={13} />
              Private workspace · Milestone 5
            </span>
            <span>Consistency compounds.</span>
          </footer>
        </div>
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
