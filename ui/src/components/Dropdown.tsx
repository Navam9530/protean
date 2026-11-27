import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";

interface Option { value: string; label: string }

/** A dropdown that matches the app (the browser's own select list cannot be styled).
 * Arrow keys move, Enter picks, Escape closes (without closing whatever is around it). */
export default function Dropdown({ value, options, onChange, disabled, label, icon }: {
  value: string; options: Option[]; onChange: (value: string) => void; disabled?: boolean; label: string; icon?: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const current = options.find((o) => o.value === value) ?? options[0];

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    window.addEventListener("mousedown", away);
    return () => window.removeEventListener("mousedown", away);
  }, [open]);

  const show = () => { setActive(Math.max(0, options.findIndex((o) => o.value === value))); setOpen(true); };
  const pick = (o: Option) => { setOpen(false); if (o.value !== value) onChange(o.value); };

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape" && open) { e.stopPropagation(); setOpen(false); return; }
    if (!open) {
      if (["ArrowDown", "ArrowUp"].includes(e.key)) { e.preventDefault(); show(); }
      return;
    }
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((active + 1) % options.length); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((active - 1 + options.length) % options.length); }
    else if (e.key === "Enter") { e.preventDefault(); pick(options[active]); }
  }

  return (
    <div className="dd" ref={root} onKeyDown={onKeyDown}>
      <button type="button" className="dd-trigger" disabled={disabled} aria-haspopup="listbox" aria-expanded={open} aria-label={label}
        onClick={() => (open ? setOpen(false) : show())}>
        {icon}
        <span className="dd-label">{label}</span>
        <span className="dd-value">{current?.label}</span>
        <ChevronDown size={14} className={`dd-chev${open ? " open" : ""}`} />
      </button>
      {open && (
        <ul className="dd-menu" role="listbox">
          {options.map((o, i) => (
            <li key={o.value} role="option" aria-selected={o.value === value} className={`${o.value === value ? "on" : ""}${i === active ? " active" : ""}`}
              onMouseEnter={() => setActive(i)} onClick={() => pick(o)}>
              <span>{o.label}</span>
              {o.value === value && <Check size={13} />}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
