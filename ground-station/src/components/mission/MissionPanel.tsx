import type { ReactNode } from "react";

interface MissionPanelProps {
  title: string;
  meta?: ReactNode;
  children: ReactNode;
}

export function MissionPanel({ title, meta, children }: MissionPanelProps) {
  return (
    <div className="flex h-full flex-col overflow-hidden rounded-[5px] border border-[color:var(--color-ink)]/25 bg-[var(--color-paper)]">
      <div className="flex h-12 min-h-12 items-center border-b border-[color:var(--color-ink)]/20 bg-[var(--color-ink)]/6 px-[18px]">
        <h2 className="text-[13px] font-semibold text-[color:var(--color-ink)]">
          {title}
        </h2>
        {meta && (
          <span className="ml-auto text-[10px] text-[color:var(--color-ink)]/70">
            {meta}
          </span>
        )}
      </div>
      {children}
    </div>
  );
}
