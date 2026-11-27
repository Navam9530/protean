import { useEffect, useState } from "react";
import { stream } from "../api";
import type { Bump } from "../backend";
import { useStore } from "../state/store";
import { StageList, useRun } from "./Progress";

interface Saved { name: string; familyVersion: string; bumped: boolean; changed: boolean }

/** Saves the draft as a family, showing the backend's checks as they run. */
export default function SaveDialog({ name, editing, onClose }: { name: string; editing: boolean; onClose: (saved: boolean) => void }) {
  const flush = useStore((s) => s.flush);
  const { run, go } = useRun();
  const [bump, setBump] = useState<Bump>("patch");
  const [started, setStarted] = useState(!editing); // a first save has nothing to choose
  const [result, setResult] = useState<Saved | null>(null);

  useEffect(() => {
    if (!started) return;
    void (async () => {
      const sent = await flush(); // the stream checks what is on disk
      if (!sent) return void go(() => Promise.reject(new Error("Your latest changes could not be saved, so nothing was checked.")));
      const saved = await go((on) => stream<Saved>(`/drafts/${name}/save`, { bump }, on));
      if (saved) setResult(saved);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [started]);

  const finished = result !== null || (!run.running && run.error !== null);
  return (
    <div className="overlay">
      <div className="dialog wide-ish" role="dialog">
        <h3>{result ? "Saved" : "Save family"}</h3>
        {!started ? (
          <>
            <p>This family was saved before. If you changed anything, its version goes up.</p>
            <div className="seg" style={{ marginBottom: 20 }}>
              {(["patch", "minor", "major"] as const).map((b) => (
                <button key={b} className={bump === b ? "on" : ""} onClick={() => setBump(b)}>{b}</button>
              ))}
            </div>
            <div className="dialog-actions">
              <button className="btn" onClick={() => onClose(false)}>Cancel</button>
              <button className="btn primary" onClick={() => setStarted(true)}>Save</button>
            </div>
          </>
        ) : (
          <>
            <StageList run={run} />
            {result && (
              <p className="save-result">
                {!result.changed ? `Nothing changed, so version ${result.familyVersion} stays as it is.`
                  : `Saved as version ${result.familyVersion}.`}
              </p>
            )}
            {run.error && <p className="hint">Your draft is untouched. Fix the problem and save again.</p>}
            <div className="dialog-actions">
              <button className="btn primary" disabled={!finished} onClick={() => onClose(result !== null)}>
                {result ? "Done" : "Close"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
