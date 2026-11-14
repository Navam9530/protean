import { useEffect, type ReactNode } from "react";

export default function ConfirmDialog({ title, children, confirmLabel = "Delete", onConfirm, onCancel }: {
  title: string; children: ReactNode; confirmLabel?: string; onConfirm: () => void; onCancel: () => void;
}) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onCancel(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onCancel]);
  return (
    <div className="overlay" onClick={onCancel}>
      <div className="dialog" role="alertdialog" onClick={(e) => e.stopPropagation()}>
        <h3>{title}</h3>
        <p>{children}</p>
        <div className="dialog-actions">
          <button className="btn" autoFocus onClick={onCancel}>Cancel</button>
          <button className="btn danger-solid" onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}
