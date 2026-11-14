import { useState } from "react";
import { LogOut, Orbit } from "lucide-react";
import { useProfile } from "../state/profile";
import ConfirmDialog from "./ConfirmDialog";

export function Avatar({ name, url, size = 28 }: { name: string; url?: string | null; size?: number }) {
  return url ? (
    <img className="avatar" src={url} width={size} height={size} alt="" />
  ) : (
    <span className="avatar" style={{ width: size, height: size, fontSize: size * 0.44 }}>{name.charAt(0).toUpperCase()}</span>
  );
}

export default function Sidebar() {
  const { owner, source, avatarUrl, openAuth, logout } = useProfile();
  const [confirming, setConfirming] = useState(false);
  return (
    <aside className="sidebar">
      <div className="sb-brand"><Orbit size={18} color="var(--accent)" /> Protean</div>
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
        <button className="sb-logout" onClick={() => setConfirming(true)}><LogOut size={14} /> Sign out</button>
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
