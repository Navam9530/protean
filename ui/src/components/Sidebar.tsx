import { useState } from "react";
import { LogOut, Menu, Orbit, PanelLeftClose } from "lucide-react";
import { useProfile } from "../state/profile";
import ConfirmDialog from "./ConfirmDialog";

export function Avatar({ name, url, size = 28 }: { name: string; url?: string | null; size?: number }) {
  return url ? (
    <img className="avatar" src={url} width={size} height={size} alt="" />
  ) : (
    <span className="avatar" style={{ width: size, height: size, fontSize: size * 0.44 }}>{name.charAt(0).toUpperCase()}</span>
  );
}

const KEY = "protean.sidebar.collapsed";
function remembered() {
  try { return localStorage.getItem(KEY) === "1"; } catch { return false; }
}

export default function Sidebar() {
  const { owner, source, avatarUrl, openAuth, logout } = useProfile();
  const [confirming, setConfirming] = useState(false);
  const [collapsed, setCollapsed] = useState(remembered);
  const toggle = () => {
    setCollapsed(!collapsed);
    try { localStorage.setItem(KEY, collapsed ? "0" : "1"); } catch { /* the choice is just not remembered */ }
  };
  return (
    <aside className={`sidebar${collapsed ? " collapsed" : ""}`}>
      <div className="sb-brand">
        {collapsed ? (
          <button className="btn ghost icon" title="Open sidebar" aria-label="Open sidebar" onClick={toggle}><Menu size={17} /></button>
        ) : (
          <>
            <Orbit size={18} color="var(--accent)" /> <span className="sb-title">Protean</span>
            <button className="btn ghost icon sb-toggle" title="Close sidebar" aria-label="Close sidebar" onClick={toggle}><PanelLeftClose size={16} /></button>
          </>
        )}
      </div>
      <nav className="sb-nav">{/* sections will be added later */}</nav>
      <button
        className="sb-profile"
        title={source === "github" ? "Signed in with GitHub" : "Not signed in. Click to sign in with GitHub"}
        onClick={() => source !== "github" && openAuth()}
      >
        <Avatar name={owner} url={avatarUrl} />
        <span className="sb-who">
          <span className="sb-name">{owner}</span>
          <span className="sb-sub">{source === "github" ? "GitHub" : "Local profile · sign in"}</span>
        </span>
      </button>
      {source === "github" && (
        <button className="sb-logout" title="Sign out" onClick={() => setConfirming(true)}><LogOut size={14} /> <span>Sign out</span></button>
      )}
      {confirming && (
        <ConfirmDialog
          title="Sign out of GitHub?"
          confirmLabel="Sign out"
          onConfirm={() => { setConfirming(false); void logout(); }}
          onCancel={() => setConfirming(false)}
        >
          Protean forgets the GitHub token and switches to your local profile. To fully revoke access, remove Protean under GitHub → Settings → Applications. Families you created while signed in stay on this computer but can no longer be published from here.
        </ConfirmDialog>
      )}
    </aside>
  );
}
