import { useRef, useState, type ChangeEvent, type DragEvent } from "react";

interface Props {
  value: File | null;
  onChange: (file: File | null) => void;
  accept?: string;
}

export function FileDrop({ value, onChange, accept = ".md,.markdown,.txt" }: Props) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) onChange(file);
  }

  function onSelect(e: ChangeEvent<HTMLInputElement>) {
    onChange(e.target.files?.[0] ?? null);
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      onClick={() => inputRef.current?.click()}
      role="button"
      tabIndex={0}
      className={[
        "cursor-pointer rounded-xl border-2 border-dashed p-8 text-center transition-colors",
        dragging
          ? "border-indigo-500 bg-indigo-50"
          : "border-slate-300 bg-slate-50/50 hover:border-slate-400 hover:bg-slate-50",
      ].join(" ")}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        onChange={onSelect}
        className="hidden"
      />
      {value ? (
        <div>
          <p className="font-medium text-slate-900">{value.name}</p>
          <p className="text-sm text-slate-500">{(value.size / 1024).toFixed(1)} KB</p>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onChange(null);
            }}
            className="mt-2 text-xs font-medium text-slate-500 underline hover:text-slate-700"
          >
            Remove
          </button>
        </div>
      ) : (
        <div className="space-y-1">
          <p className="font-medium text-slate-700">Drop a requirements document here</p>
          <p className="text-sm text-slate-500">or click to browse · .md / .txt / .pdf / .docx</p>
        </div>
      )}
    </div>
  );
}
