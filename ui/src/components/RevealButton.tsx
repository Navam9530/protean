import { FolderOpen } from "lucide-react";
import { revealFolder } from "../backend";
import type { RevealTarget } from "../backend";
import { useStore } from "../state/store";

type Props = Omit<RevealTarget, "scope"> & { scope?: RevealTarget["scope"]; className?: string; size?: number };

/** Opens the folder in the file explorer. Inside the canvas the scope is the draft once it exists,
 * otherwise the saved family (an unchanged saved family has no draft folder yet). */
export default function RevealButton({ scope, className = "btn ghost icon", size = 14, ...target }: Props) {
  const materialized = useStore((s) => s.materialized);
  const where = scope ?? (materialized ? "draft" : "family");
  return (
    <button className={className} title="Show in file explorer"
      onClick={(e) => { e.stopPropagation(); revealFolder({ ...target, scope: where }).catch((err: Error) => alert(err.message)); }}>
      <FolderOpen size={size} />
    </button>
  );
}
