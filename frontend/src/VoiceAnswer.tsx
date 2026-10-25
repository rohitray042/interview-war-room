import { useEffect, useRef, useState } from "react";
import { Mic, Square, Volume2 } from "lucide-react";

type Recognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult:
    | ((event: {
        results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }>;
      }) => void)
    | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
};
type SpeechWindow = Window & {
  SpeechRecognition?: new () => Recognition;
  webkitSpeechRecognition?: new () => Recognition;
};

export default function VoiceAnswer({
  question,
  value,
  onChange,
  disabled,
  onCapture,
}: {
  question: string;
  value: string;
  onChange: (text: string) => void;
  disabled: boolean;
  onCapture: (active: boolean) => void;
}) {
  const [consent, setConsent] = useState(false);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState("");
  const [language, setLanguage] = useState("en-IN");
  const recognition = useRef<Recognition | null>(null);
  const stopped = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const synth = window.speechSynthesis;
  const Speech =
    (window as SpeechWindow).SpeechRecognition ||
    (window as SpeechWindow).webkitSpeechRecognition;
  function stop() {
    stopped.current = true;
    recognition.current?.stop();
    synth?.cancel();
    setSpeaking(false);
  }
  useEffect(() => {
    const hide = () => {
      if (document.hidden) stop();
    };
    document.addEventListener("visibilitychange", hide);
    return () => {
      document.removeEventListener("visibilitychange", hide);
      clearTimeout(timer.current);
      if (recognition.current) {
        recognition.current.onresult = null;
        recognition.current.onend = null;
        recognition.current.onerror = null;
        recognition.current.abort();
      }
      synth?.cancel();
      onCapture(false);
    };
  }, []);
  useEffect(() => {
    if (disabled) stop();
  }, [disabled]);
  function read() {
    stop();
    if (!synth) return;
    const utterance = new SpeechSynthesisUtterance(question);
    utterance.lang = language;
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => {
      setSpeaking(false);
      setError(
        "Question audio could not play. You can read the question above.",
      );
    };
    setSpeaking(true);
    synth.speak(utterance);
  }
  function start() {
    if (!Speech || !consent || disabled || recognition.current) return;
    synth?.cancel();
    setSpeaking(false);
    setError("");
    stopped.current = false;
    const instance = new Speech();
    recognition.current = instance;
    instance.lang = language;
    instance.continuous = true;
    instance.interimResults = true;
    const original = value.trim();
    instance.onresult = (event) => {
      const final: string[] = [],
        pending: string[] = [];
      for (const result of Array.from(event.results)) {
        (result.isFinal ? final : pending).push(result[0].transcript);
      }
      const text = [original, ...final].filter(Boolean).join(" ");
      onChange(text.slice(0, 20000));
      setInterim(pending.join(" "));
      if (text.length >= 20000) {
        setError("Answer limit reached. Review the transcript.");
        instance.stop();
      }
    };
    instance.onerror = ({ error: code }) => {
      if (code === "aborted" && stopped.current) return;
      const messages: Record<string, string> = {
        "not-allowed": "Microphone permission denied. Allow microphone access for this site and your browser in device settings, then retry.",
        "service-not-allowed": "Your browser blocked its speech service. Open this page in Chrome or Safari outside an embedded preview, then retry.",
        "audio-capture": "No working microphone is available. Check your input device and whether another app is using it, then retry.",
        network: "The browser speech service could not connect. Open the app in a full browser instead of a VS Code preview. Check your network or VPN, then retry. This speech service is separate from Gemini.",
        "no-speech": "No speech detected. Check your microphone input and try again.",
        "language-not-supported": "This speech service does not support the selected language. Select another speech language and retry.",
        aborted: "Speech capture was interrupted. Tap Start microphone to retry.",
      };
      setError(messages[code] || `Speech recognition failed (${code}). Retry or type your answer.`);
      clearTimeout(timer.current);
      instance.onresult = null;
      instance.onend = null;
      instance.onerror = null;
      instance.abort();
      recognition.current = null;
      setListening(false);
      setInterim("");
      onCapture(false);
    };
    instance.onend = () => {
      recognition.current = null;
      clearTimeout(timer.current);
      setListening(false);
      setInterim("");
      onCapture(false);
    };
    try {
      instance.start();
      setListening(true);
      onCapture(true);
      timer.current = setTimeout(() => instance.stop(), 5 * 60 * 1000);
    } catch {
      recognition.current = null;
      setListening(false);
      onCapture(false);
      setError("Microphone could not start. Try again or type your answer.");
    }
  }
  return (
    <section className="voice-answer" aria-label="Voice interview">
      <div className="interview-actions">
        <button
          type="button"
          className="secondary"
          disabled={disabled || !synth || listening}
          onClick={speaking ? stop : read}
        >
          {speaking ? <Square size={16} /> : <Volume2 size={16} />}
          {speaking ? "Stop audio" : "Read question"}
        </button>
        <label>
          Speech language
          <select
            value={language}
            disabled={listening || speaking}
            onChange={(e) => setLanguage(e.target.value)}
          >
            <option value="en-IN">English (India)</option>
            <option value="en-US">English (US)</option>
            <option value="hi-IN">Hindi</option>
          </select>
        </label>
      </div>
      {Speech ? (
        <>
          <label className="interview-check">
            <input
              type="checkbox"
              checked={consent}
              disabled={listening}
              onChange={(e) => setConsent(e.target.checked)}
            />
            Allow browser speech processing. Audio may be sent to your browser's
            speech service. This app saves transcript text, not audio recordings.
          </label>
          <button
            type="button"
            className="secondary"
            aria-pressed={listening}
            disabled={disabled || !consent}
            onClick={listening ? stop : start}
          >
            {listening ? <Square size={16} /> : <Mic size={16} />}
            {listening ? "Stop microphone" : "Start microphone"}
          </button>
        </>
      ) : (
        <p>
          Speech recognition is unavailable in this browser. You can type your
          answer below.
        </p>
      )}
      <p role="status">
        {listening
          ? "Listening..."
          : speaking
            ? "Reading question..."
            : "Microphone off"}
      </p>
      {interim && <p className="voice-interim">{interim}</p>}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
