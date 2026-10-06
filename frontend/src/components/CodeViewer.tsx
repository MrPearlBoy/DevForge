import { useEffect, useMemo, useRef, type ReactNode } from "react";
import { FileCode2, FileText, Loader2 } from "lucide-react";
import type { FileNode } from "../lib/types";

const PY_KEYWORDS = new Set([
  "def", "class", "return", "if", "elif", "else", "for", "while", "import", "from", "as",
  "with", "try", "except", "finally", "raise", "lambda", "yield", "pass", "break", "continue",
  "global", "nonlocal", "assert", "del", "in", "is", "not", "and", "or", "None", "True", "False",
]);

const TOKEN_RE =
  /("""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|#.*$|\b\d+(?:\.\d+)?\b|\b[A-Za-z_][A-Za-z0-9_]*\b|[^\sA-Za-z0-9_]+|\s+)/g;

function highlightLine(line: string, key: number): ReactNode {
  const nodes: ReactNode[] = [];
  let m: RegExpExecArray | null;
  TOKEN_RE.lastIndex = 0;
  let i = 0;
  while ((m = TOKEN_RE.exec(line)) !== null) {
    const tok = m[0];
    let cls = "text-slate-200";
    if (tok.startsWith("#")) cls = "text-slate-500 italic";
    else if (/^["']/.test(tok)) cls = "text-emerald-300/90";
    else if (/^\d/.test(tok)) cls = "text-amber-300";
    else if (PY_KEYWORDS.has(tok)) cls = "text-violet-400";
    else if (/^[A-Z][A-Za-z0-9_]*$/.test(tok)) cls = "text-cyan-300";
    else if (/^[a-z_]/.test(tok) && line[m.index + tok.length] === "(") cls = "text-sky-300";
    nodes.push(
      <span key={`${key}-${i++}`} className={cls}>
        {tok}
      </span>
    );
  }
  return <div className="whitespace-pre">{nodes.length ? nodes : " "}</div>;
}

interface Props {
  files: FileNode[];
  selected: string | null;
  content: string | null;
  loading?: boolean;
  onSelect: (path: string) => void;
}

export default function CodeViewer({ files, selected, content, loading, onSelect }: Props) {
  const preRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    preRef.current?.scrollTo({ top: 0 });
  }, [selected]);

  const isPy = (p: string) => p.endsWith(".py");
  const isMd = (p: string) => p.endsWith(".md");

  const tree = useMemo(() => {
    const order = (f: FileNode) =>
      f.path.startsWith("src/") ? 0 : f.path.startsWith("tests/") ? 1 : f.path.startsWith("docs/") ? 3 : f.path.startsWith("requirements/") || f.path.startsWith("architecture/") ? 2 : 4;
    return [...files].sort((a, b) => order(a) - order(b) || a.path.localeCompare(b.path));
  }, [files]);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-lg border border-ink-700/60 bg-ink-950">
      <div className="grid min-h-0 flex-1 grid-cols-[220px_1fr]">
        {/* file tree */}
        <div className="min-h-0 overflow-y-auto border-r border-ink-700/60 p-2">
          {tree.length === 0 && <p className="p-2 text-xs text-slate-600">No files yet — the Coding Agent writes here.</p>}
          {tree.map((f) => {
            const depth = f.path.split("/").length - 1;
            const active = f.path === selected;
            return (
              <button
                key={f.path}
                onClick={() => onSelect(f.path)}
                style={{ paddingLeft: `${8 + depth * 12}px` }}
                className={`flex w-full items-center gap-1.5 rounded-md py-1 pr-2 text-left font-mono text-[11.5px] transition-colors ${
                  active ? "bg-indigo-500/15 text-indigo-200" : "text-slate-400 hover:bg-ink-800 hover:text-slate-200"
                }`}
              >
                {isPy(f.path) ? (
                  <FileCode2 size={12} className={active ? "text-indigo-300" : "text-slate-500"} />
                ) : (
                  <FileText size={12} className={active ? "text-indigo-300" : "text-slate-500"} />
                )}
                <span className="truncate">{f.path}</span>
                <span className="ml-auto shrink-0 text-[9.5px] text-slate-600">{f.size > 1024 ? `${(f.size / 1024).toFixed(1)}k` : f.size}</span>
              </button>
            );
          })}
        </div>

        {/* content */}
        <div ref={preRef} className="min-h-0 overflow-auto p-3">
          {loading && (
            <div className="flex items-center gap-2 p-4 text-sm text-slate-500">
              <Loader2 size={15} className="animate-spin" /> loading file…
            </div>
          )}
          {!loading && !selected && (
            <p className="p-4 text-sm text-slate-600">Select a file from the workspace tree.</p>
          )}
          {!loading && selected && content !== null && (
            <div className="font-mono text-[12px] leading-[1.55]">
              {isPy(selected) || isMd(selected) ? (
                <div className="flex">
                  <div className="select-none pr-3 text-right text-slate-600">
                    {content.split("\n").map((_, i) => (
                      <div key={i}>{i + 1}</div>
                    ))}
                  </div>
                  <div className="flex-1">
                    {content.split("\n").map((ln, i) =>
                      isPy(selected) ? (
                        <div key={i}>{highlightLine(ln, i)}</div>
                      ) : (
                        <div key={i} className="whitespace-pre text-slate-300">
                          {ln || " "}
                        </div>
                      )
                    )}
                  </div>
                </div>
              ) : (
                <pre className="whitespace-pre-wrap text-slate-300">{content}</pre>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
