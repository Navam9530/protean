import { useEffect, useRef, useState } from "react";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import { AlertTriangle, ArrowLeft, Check, ExternalLink, FolderUp, Import, Search, Star, Tag, X } from "lucide-react";
import { getRepoDetail, importFolder, importRepo, searchRepos, type ImportedFamily, type RepoDetail, type RepoSummary, type SearchResult } from "../marketplaceApi";
import { createDraft, discardImport } from "../backend";
import { ago } from "../state/family";
import { ownsRepo, useProfile } from "../state/profile";
import { useMarketplace } from "../state/marketplace";
import { useStore } from "../state/store";
import { Avatar } from "./Sidebar";
import Dropdown from "./Dropdown";
import MergeDialog from "./MergeDialog";
import ImportDialog from "./ImportDialog";
import { useRun } from "./Progress";

/** What each expected file means. `blocking` ones disable Import, the rest only warn. */
const CHECKS = [
  { key: "familyJson", label: "family.json", blocking: true, missing: "Not a family: family.json was not found." },
  { key: "license", label: "LICENSE", blocking: false, missing: "No license, so you may not be allowed to reuse it." },
  { key: "prompts", label: "prompts/", blocking: true, missing: "No prompts folder. Every agent needs a prompt file, so this can’t be imported." },
  { key: "readme", label: "README.md", blocking: false, missing: "No README." },
] as const;

export default function MarketplaceDrawer() {
  const { target, close } = useMarketplace();
  const { adopt, adoptMerged, draft, flush, ensureDraft } = useStore();
  const owner = useProfile((p) => p.owner);
  const { run, go, reset } = useRun();
  const [popup, setPopup] = useState<string | null>(null); // title of the import popup while it is open
  const [result, setResult] = useState<ImportedFamily | null>(null); // the finished import, waiting for a choice
  const [actionError, setActionError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [picked, setPicked] = useState<RepoSummary | null>(null);
  const [detail, setDetail] = useState<RepoDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [versions, setVersions] = useState<string[]>([]); // the repo's tags; none means only the latest
  const [version, setVersion] = useState(""); // "" is the default branch
  const chosen = useRef(""); // the same, for answers that arrive late
  const [pending, setPending] = useState<ImportedFamily | null>(null); // imported, waiting to be merged
  const profile = useProfile();
  const busy = run.running;

  useEffect(() => {
    let live = true;
    setResults(null);
    setListError(null);
    const t = setTimeout(() => {
      searchRepos(query).then((r) => live && setResults(r), (e: Error) => live && setListError(e.message));
    }, 400); // GitHub search is rate limited, so wait for the typing to pause
    return () => { live = false; clearTimeout(t); };
  }, [query]);

  async function showMore() {
    if (!results) return;
    setLoadingMore(true);
    try {
      const next = await searchRepos(query, results.page + 1);
      setResults({ ...next, items: [...results.items, ...next.items] });
    } catch (e) {
      setListError((e as Error).message);
    } finally {
      setLoadingMore(false);
    }
  }

  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape" && !pending) close(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [close, pending]);

  if (!target) return null;
  const underAgent = target.kind === "agent";

  function pick(r: RepoSummary) {
    setPicked(r); setDetail(null); reset(); setDetailError(null); setVersions([]); setVersion(""); chosen.current = "";
    getRepoDetail(r.owner, r.repo).then((d) => { setDetail(d); setVersions(d.versions); }, (e: Error) => setDetailError(e.message));
  }

  /** Check the files and README of the chosen version before the import button comes back. */
  function chooseVersion(r: RepoSummary, v: string) {
    setVersion(v); setDetail(null); setDetailError(null);
    chosen.current = v;
    getRepoDetail(r.owner, r.repo, v || undefined).then(
      (d) => { if (chosen.current === v) setDetail(d); }, // a slow answer for an earlier choice is ignored
      (e: Error) => { if (chosen.current === v) setDetailError(e.message); },
    );
  }

  /** Run an import inside the popup. When it succeeds the import waits in imports/ for the user's choice. */
  async function start(title: string, operation: Parameters<typeof go<ImportedFamily>>[0]) {
    setPopup(title); setResult(null); setActionError(null);
    const data = await go(operation);
    if (data) setResult(data);
  }
  const doImport = (r: RepoSummary) => start(`Importing ${r.owner}/${r.repo}`, (on) => importRepo(r.owner, r.repo, version || undefined, on));
  async function doUpload(files: File[]) {
    if (!files.length) return;
    const folder = files[0].webkitRelativePath.split("/")[0]; // only for the title: the backend names the family
    await start(`Importing ${folder} from your computer`, (on) => importFolder(files, on));
  }

  async function discard() {
    if (result) await discardImport(result.importId);
    setPopup(null); setResult(null);
  }

  /** A new family: the import becomes a draft, which opens on the canvas. */
  async function openOnCanvas(data: ImportedFamily) {
    try {
      await adopt(await createDraft({ kind: "import", importId: data.importId, owner: data.owner, repo: data.repo }));
      setPopup(null); setResult(null);
      close();
    } catch (e) { setActionError((e as Error).message); }
  }

  /** Under an agent: the user chooses how to merge it, on the draft as it is on disk. */
  async function chooseMerge(data: ImportedFamily) {
    await ensureDraft().catch(() => null); // the merge works on the draft folder
    if (!(await flush())) return setActionError("Your latest changes could not be saved, so nothing can be merged yet.");
    setPending(data); setPopup(null); setResult(null);
  }

  async function cancelMerge() {
    if (pending) await discardImport(pending.importId);
    setPending(null);
  }

  const blocked = !!detail && CHECKS.some((c) => c.blocking && !detail.has[c.key]);

  return (
    <>
    <aside className="mp">
      <div className="mp-head">
        {picked && <button className="btn ghost icon" title="Back to results" onClick={() => setPicked(null)}><ArrowLeft size={16} /></button>}
        <div className="mp-title">
          <b>{picked ? `${picked.owner}/${picked.repo}` : "Import a family"}</b>
          {!picked && <span>{underAgent ? `Adds its agents under “${target.parentId}”` : "Opens it on the canvas under the publisher’s name"}</span>}
        </div>
        <button className="btn ghost icon" title="Close" onClick={close}><X size={16} /></button>
      </div>

      {!picked ? (
        <>
          <div className="mp-search">
            <Search size={14} />
            <input autoFocus placeholder="Search the marketplace…" value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
          <div className="mp-list">
            <div className="mp-upload">
              <b>Not on GitHub yet?</b>
              <div>
                <label className={`btn ${busy ? "disabled" : ""}`}>
                  <FolderUp size={14} /> Choose a family folder
                  <input type="file" hidden disabled={busy}
                    // @ts-expect-error webkitdirectory is not in the DOM typings
                    webkitdirectory="" onChange={(e) => { void doUpload(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
                </label>
              </div>
              <p className="hint" style={{ margin: "6px 0 0" }}>The family is named after the folder: {owner}_folder-name.</p>
            </div>
            {listError && <div className="mp-error"><AlertTriangle size={14} /> {listError}</div>}
            {results === null && !listError && <div className="mp-note">Searching…</div>}
            {results?.items.length === 0 && <div className="mp-note">No families match “{query}”.</div>}
            {results?.items.map((r) => (
              <button key={`${r.owner}/${r.repo}`} className="mp-item" onClick={() => pick(r)}>
                <Avatar name={r.owner} url={r.avatarUrl} size={30} />
                <div className="mp-item-body">
                  <div className="mp-item-top">
                    <span className="mp-repo">{r.repo}</span>
                    <span className="mp-owner">{r.owner}</span>
                    {!r.license && <AlertTriangle size={13} className="mp-warn" aria-label="No license" />}
                  </div>
                  <p>{r.description || "No description"}</p>
                  <div className="mp-meta">
                    <span><Star size={11} /> {r.stars}</span>
                    <span>{r.license ?? "No license"}</span>
                    <span>updated {ago(r.pushedAt)}</span>
                  </div>
                </div>
              </button>
            ))}
            {results && results.items.length < results.total && (
              <button className="btn mp-more" disabled={loadingMore} onClick={() => void showMore()}>
                {loadingMore ? "Loading…" : `Show more (${results.total - results.items.length} left)`}
              </button>
            )}
          </div>
        </>
      ) : (
        <div className="mp-detail">
          <div className="mp-detail-top">
            <Avatar name={picked.owner} url={picked.avatarUrl} size={36} />
            <div>
              <h3>{picked.repo}</h3>
              <p>{picked.description || "No description"}</p>
              <div className="mp-meta">
                <span><Star size={11} /> {picked.stars}</span>
                <span>{picked.license ?? "No license"}</span>
                <span>updated {ago(picked.pushedAt)}</span>
                <a href={`https://github.com/${picked.owner}/${picked.repo}`} target="_blank" rel="noreferrer"><ExternalLink size={11} /> GitHub</a>
              </div>
            </div>
          </div>

          {versions.length > 0 && (
            <Dropdown label="Version" icon={<Tag size={13} />} value={version} disabled={busy}
              options={[{ value: "", label: "Latest" }, ...versions.map((v) => ({ value: v, label: v }))]}
              onChange={(v) => chooseVersion(picked, v)} />
          )}

          {detailError ? (
            <div className="mp-error"><AlertTriangle size={14} /> {detailError}</div>
          ) : !detail ? (
            <div className="mp-note">Checking the repository…</div>
          ) : (
            <>
              <ul className="mp-checks">
                {CHECKS.map((c) => {
                  const ok = detail.has[c.key];
                  return (
                    <li key={c.key} className={ok ? "ok" : c.blocking ? "bad" : "warn"} title={ok ? undefined : c.missing}>
                      {ok ? <Check size={13} /> : <AlertTriangle size={13} />}
                      <code>{c.label}</code>
                    </li>
                  );
                })}
              </ul>
              {CHECKS.filter((c) => !detail.has[c.key]).map((c) => (
                <p key={c.key} className={`mp-problem ${c.blocking ? "bad" : "warn"}`}><AlertTriangle size={12} /> {c.missing}</p>
              ))}
              <button className="btn primary mp-import" disabled={blocked || busy} onClick={() => void doImport(picked)}>
                <Import size={14} /> {busy ? "Importing…" : underAgent ? `Import under “${target.parentId}”` : "Import family"}
              </button>
              <p className="mp-hint">
                {underAgent
                  ? "You choose next whether to add it as a sub-agent or merge it into this agent."
                  : ownsRepo(profile, picked.owner)
                    ? <>Saved as {picked.owner}_{picked.repo}. <b>You can run it</b>, and because this is your own repository you can push changes back to it. Open it on the canvas, then Save.</>
                    : <>Saved as {picked.owner}_{picked.repo}. <b>You can run it</b>, but you can’t publish it, since it isn’t yours. Open it on the canvas, then Save.</>}
              </p>
              {detail.readme && <div className="markdown"><ReactMarkdown
                  urlTransform={(url, key) => (key === "src" && !/^([a-z][a-z0-9+.-]*:|\/\/)/i.test(url)
                    ? `https://raw.githubusercontent.com/${picked.owner}/${picked.repo}/${version || "HEAD"}/${url.replace(/^\.?\//, "")}`
                    : defaultUrlTransform(url))}
                  components={{ a: (p) => <a {...p} target="_blank" rel="noreferrer" /> }}
                >{detail.readme}</ReactMarkdown></div>}
            </>
          )}
        </div>
      )}

    </aside>
      {pending && target?.kind === "agent" && draft && (
        <MergeDialog draft={draft.name} importId={pending.importId} label={`${pending.owner}/${pending.repo}`} parentId={target.parentId}
          onCancel={() => void cancelMerge()}
          onMerged={(out) => { void adoptMerged(out); setPending(null); close(); }} />
      )}
      {popup && (
        <ImportDialog title={popup} run={run} done={result !== null} actionError={actionError} onClose={() => void discard()}
          actions={result && (
            <>
              <button className="btn" onClick={() => void discard()}>Discard</button>
              {target?.kind === "agent"
                ? <button className="btn primary" onClick={() => void chooseMerge(result)}>Choose how to add it</button>
                : <button className="btn primary" onClick={() => void openOnCanvas(result)}>Open on canvas</button>}
            </>
          )} />
      )}
    </>
  );
}
