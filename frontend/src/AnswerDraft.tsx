import { useEffect, useRef, useState } from "react";
import { answerDraft } from "./deviceStorage";

export default function AnswerDraft({
  turn,
  value,
  onRestore,
}: {
  turn: string;
  value: string;
  onRestore: (value: string) => void;
}) {
  const [loaded, setLoaded] = useState(false);
  const [status, setStatus] = useState("Loading saved draft...");
  const revision = useRef(0);
  const latest = useRef(value);
  const saved = useRef("");
  const blocked = useRef(false);
  const queue = useRef(Promise.resolve());
  latest.current = value;
  useEffect(() => {
    let active = true;
    answerDraft(turn)
      .then((draft) => {
        if (!active) return;
        revision.current = draft.revision;
        saved.current = draft.answer;
        if (!latest.current) onRestore(draft.answer);
        setLoaded(true);
        setStatus(draft.answer ? "Draft restored" : "");
      })
      .catch((e) => {
        if (active) {
          blocked.current = true;
          setStatus(e.message);
        }
      });
    return () => {
      active = false;
    };
  }, [turn]);
  useEffect(() => {
    if (!loaded || blocked.current || value === saved.current) return;
    setStatus("Saving draft...");
    let active = true;
    const timer = setTimeout(() => {
      queue.current = queue.current.then(async () => {
        if (blocked.current) return;
        try {
          const result = await answerDraft(turn, {
            answer: value,
            revision: revision.current,
          });
          revision.current = result.revision;
          saved.current = value;
          if (active) setStatus("Draft saved");
        } catch (e) {
          blocked.current = true;
          if (active)
            setStatus(
              e instanceof Error
                ? e.message
                : "Draft save failed. Copy your answer before leaving.",
            );
        }
      });
    }, 800);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [value, loaded, turn]);
  return <p role="status">{status}</p>;
}
