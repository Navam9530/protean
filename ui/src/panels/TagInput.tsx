import { useState } from "react";
import { X } from "lucide-react";

export default function TagInput({ value, onChange, placeholder }: { value: string[]; onChange: (v: string[]) => void; placeholder?: string }) {
  const [text, setText] = useState("");
  const commit = () => {
    const t = text.trim();
    if (t && !value.includes(t)) onChange([...value, t]);
    setText("");
  };
  return (
    <div className="tagin">
      {value.map((v) => (
        <span key={v} className="chip">{v}<button onClick={() => onChange(value.filter((x) => x !== v))}><X size={11} /></button></span>
      ))}
      <input
        value={text}
        placeholder={value.length ? "" : placeholder}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") { e.preventDefault(); commit(); }
          if (e.key === "Backspace" && !text && value.length) onChange(value.slice(0, -1));
        }}
        onBlur={commit}
      />
    </div>
  );
}
