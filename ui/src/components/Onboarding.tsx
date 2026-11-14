import { useEffect, useState } from "react";
import { AlertTriangle, Check, Copy } from "lucide-react";
import { useProfile } from "../state/profile";

const GithubMark = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden>
    <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 7.6 0 0 1 4 0c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
  </svg>
);

const BENEFITS = [
  "See your GitHub username and profile picture in Protean",
  "Search the agent marketplace with higher GitHub rate limits",
  "Publish a family as a new GitHub repository, starting at v0.1.0",
  "Update the files and version of repositories you’ve published",
];

export default function Onboarding() {
  const { startLogin, continueWithHostname, closeAuth, backToChoice, source, login } = useProfile();
  const reopened = source !== null; // shown again from the profile button after skipping
  useEffect(() => {
    if (!reopened) return;
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") closeAuth(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [reopened, closeAuth]);

  const [copied, setCopied] = useState(false);
  const copy = (text: string) => {
    void navigator.clipboard.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); });
  };

  if (login) {
    return (
      <div className="overlay onboarding">
        <div className="dialog wide" onClick={(e) => e.stopPropagation()}>
          <h2>Sign in with GitHub</h2>
          {login.state === "pending" ? (
            <>
              <p className="lead">Open GitHub and enter this code to approve Protean.</p>
              <div className="user-code">
                {login.userCode}
                <button className={`icon-btn${copied ? " ok" : ""}`} title="Copy code" aria-label="Copy code" onClick={() => copy(login.userCode ?? "")}>
                  {copied ? <Check size={18} /> : <Copy size={18} />}
                </button>
              </div>
              <p className="fine">
                <a href={login.verificationUri} target="_blank" rel="noreferrer">{login.verificationUri}</a>
                {" "}· waiting for approval… (expires in {Math.ceil((login.expiresIn ?? 0) / 60)} min)
              </p>
            </>
          ) : (
            <div className="warn">
              <AlertTriangle size={16} />
              <div>
                {login.state === "denied" && "You denied the request on GitHub."}
                {login.state === "expired" && "The code expired before it was approved."}
                {login.state === "error" && (login.error ?? "Something went wrong.")}
                {login.state === "idle" && "No sign-in in progress."}
              </div>
            </div>
          )}
          <div className="onb-actions">
            {login.state !== "pending" && <button className="btn primary big" onClick={startLogin}>Try again</button>}
            <button className="btn big" onClick={backToChoice}>{login.state === "pending" ? "Cancel" : "Back"}</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="overlay onboarding" onClick={reopened ? closeAuth : undefined}>
      <div className="dialog wide" onClick={(e) => e.stopPropagation()}>
        <h2>{reopened ? "Sign in with GitHub" : "Welcome to Protean"}</h2>
        <p className="lead">Sign in with GitHub to unlock sharing. It’s completely optional.</p>
        <ul className="benefits">
          {BENEFITS.map((b) => (
            <li key={b}><Check size={15} />{b}</li>
          ))}
        </ul>
        <div className="warn">
          <AlertTriangle size={16} />
          <div>
            <b>Choose carefully.</b> Families created without GitHub sign-in <b>can never be published</b> to GitHub, even if you sign in later.
            Only families created <i>after</i> signing in can be published.{reopened && " Families you’ve already created stay local-only."}
          </div>
        </div>
        <div className="onb-actions">
          <button className="btn primary big" onClick={startLogin}><GithubMark /> Continue with GitHub</button>
          {reopened ? (
            <button className="btn big" onClick={closeAuth}>Not now</button>
          ) : (
            <button className="btn big" onClick={continueWithHostname}>Skip, use my computer name</button>
          )}
        </div>
        <p className="fine">Sign-in happens on github.com. Protean never sees your password. It asks for the <code>public_repo</code> permission so it can create and update your public family repositories.</p>
      </div>
    </div>
  );
}
