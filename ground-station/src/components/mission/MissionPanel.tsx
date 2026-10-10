import type { ReactNode } from "react";

interface MissionPanelProps {
  title: string;
  meta?: ReactNode;
  darkHeader?: boolean;
  children: ReactNode;
}

export function MissionPanel({
  title,
  meta,
  children,
  darkHeader = false,
}: MissionPanelProps) {
  return (
    <div className="flex h-full flex-col overflow-hidden rounded-[5px] border border-[color:var(--color-ink)]/25 bg-[var(--color-paper)]">
      <div
        className={
          darkHeader
            ? "flex h-[42px] min-h-[42px] items-center bg-[var(--color-ink)] px-3.5"
            : "flex h-12 min-h-12 items-center border-b border-[color:var(--color-ink)]/20 bg-[var(--color-ink)]/6 px-[18px]"
        }
      >
        <h2
          className={
            darkHeader
              ? "text-xs font-normal text-[color:var(--color-paper)]"
              : "text-[13px] font-semibold text-[color:var(--color-ink)]"
          }
        >
          {title}
        </h2>
        {meta && (
          <span
            className={
              "ml-auto text-[10px] " +
              (darkHeader
                ? "text-[color:var(--color-paper)]/80"
                : "text-[color:var(--color-ink)]/80")
            }
          >
            {meta}
          </span>
        )}
      </div>
      {children}
    </div>
  );
}
