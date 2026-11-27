import { useEffect, useState } from "react";
import { AlertTriangle, ExternalLink, ShieldCheck } from "lucide-react";
import { stream } from "../api";
import { getFamilyFiles, listAgain, unpublish, type FamilyFiles } from "../backend";
import { StageList, useRun } from "./Progress";

interface Published { url: string; commit: string; tag: string; familyVersion: string; listed: boolean }
type Choice = "keep" | "mit" | "apache-2.0";
const LICENSE_NAMES = { mit: "MIT", "apache-2.0": "Apache 2.0", other: "a custom license" } as const;

/** Whether the published repo is in the marketplace, and the two things the user can do about it. */
function Listing({ name, listed, onChange }: { name: string; listed: boolean; onChange: (listed: boolean) => void }) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function change(job: () => Promise<{ listed: boolean }>) {
    setBusy(true); setError(null);
    try { onChange((await job()).listed); setAsking(false); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  return (
    <div className="listing">
      <div className="listing-row">
        <span>{listed ? "Listed in the marketplace" : "Not listed in the marketplace"}</span>
        {listed ? (
          !asking && <button className="btn" onClick={() => setAsking(true)}>Unpublish</button>
        ) : (
          <button className="btn" disabled={busy} onClick={() => void change(() => listAgain(name))}>{busy ? "Listing…" : "List in the marketplace"}</button>
        )}
      </div>
      {asking && (
        <div className="notice">
          Unpublishing removes the “agents-marketplace” topic, so people can no longer find this family in the marketplace.
          The repository, its history and your local family stay as they are, and you can list it again any time.
          <div className="dialog-actions" style={{ marginTop: 10 }}>
            <button className="btn" onClick={() => setAsking(false)}>Keep it listed</button>
            <button className="btn primary" disabled={busy} onClick={() => void change(() => unpublish(name))}>{busy ? "Unpublishing…" : "Unpublish"}</button>
          </div>
        </div>
      )}
      {error && <div className="mp-error"><AlertTriangle size={14} /> {error}</div>}
    </div>
  );
}

/** Publishes a saved family to the user's own GitHub repo. Only what the user changed is sent. */
/** `listed` is null until the family has been published from here. */
export default function PublishDialog({ name, listed: initiallyListed, onClose }: { name: string; listed: boolean | null; onClose: () => void }) {
  const { run, go } = useRun();
  const [files, setFiles] = useState<FamilyFiles | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [about, setAbout] = useState("");
  const [readme, setReadme] = useState("");
  const [license, setLicense] = useState<Choice>("keep");
  const [started, setStarted] = useState(false);
  const [result, setResult] = useState<Published | null>(null);
  const [listed, setListed] = useState(initiallyListed);

  useEffect(() => {
    getFamilyFiles(name).then((f) => { setFiles(f); setAbout(f.description); setReadme(f.readme); }, (e: Error) => setLoadError(e.message));
  }, [name]);

  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape" && !run.running) onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose, run.running]);

  async function publish() {
    if (!files) return;
    const body: { description?: string; readme?: string; license?: string } = {};
    if (about !== files.description) body.description = about;
    if (readme !== files.readme) body.readme = readme;
    if (license !== "keep") body.license = license;
    setStarted(true);
    const done = await go((on) => stream<Published>(`/families/${name}/publish`, body, on));
    if (done) setResult(done);
  }

  const finished = result !== null || (started && !run.running && run.error !== null);
  return (
    <div className="overlay">
      <div className="dialog wide-ish" role="dialog">
        <h3>{result ? "Published" : "Publish to GitHub"}</h3>
        {!started ? (
          <>
            {loadError && <div className="mp-error">{loadError}</div>}
            {files && (
              <>
                <p className="hint" style={{ marginBottom: 14 }}>
                  Pushes <b>{name}</b> to <b>github.com/{name.replace("_", "/")}</b> as a new commit, so earlier versions stay in its history.
                  The first time, Protean creates the repository.
                </p>
                {listed !== null && <Listing name={name} listed={listed} onChange={setListed} />}
                <div className="field">
                  <label>License</label>
                  <select className="select" value={license} onChange={(e) => setLicense(e.target.value as Choice)}>
                    <option value="keep">{files.license ? `Keep the current license (${LICENSE_NAMES[files.license]})` : "No license (keep what the repo has)"}</option>
                    <option value="mit">MIT</option>
                    <option value="apache-2.0">Apache 2.0</option>
                  </select>
                </div>
                <div className="field">
                  <label>About</label>
                  <input className="input" maxLength={350} value={about} placeholder="One line shown on the repository and in the marketplace (optional)" onChange={(e) => setAbout(e.target.value)} />
                </div>
                <div className="field">
                  <label>README</label>
                  <textarea className="textarea mono" rows={8} value={readme} placeholder="Describe what this family does (optional)" onChange={(e) => setReadme(e.target.value)} />
                </div>
                <div className="notice"><ShieldCheck size={13} style={{ verticalAlign: -2 }} /> Protean can only create or update repositories. It never deletes anything on GitHub and never asks for permission to.</div>
              </>
            )}
            <div className="dialog-actions">
              <button className="btn" onClick={onClose}>Cancel</button>
              <button className="btn primary" disabled={!files} onClick={() => void publish()}>Publish</button>
            </div>
          </>
        ) : (
          <>
            <StageList run={run} />
            {result && (
              <p className="save-result">
                Published version {result.familyVersion} (tag {result.tag}).{" "}
                <a href={result.url} target="_blank" rel="noreferrer">Open on GitHub <ExternalLink size={11} /></a>
              </p>
            )}
            {result && !result.listed && <Listing name={name} listed={false} onChange={(l) => setResult({ ...result, listed: l })} />}
            {run.error && <p className="hint">Nothing on this device changed. Fix the problem and publish again.</p>}
            <div className="dialog-actions">
              <button className="btn primary" disabled={!finished} onClick={onClose}>{result ? "Done" : "Close"}</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
