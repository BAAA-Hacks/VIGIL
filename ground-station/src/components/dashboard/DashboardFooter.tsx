import { ShieldCheck } from "lucide-react";
export function DashboardFooter() {
  return (
    <footer className="flex justify-between py-6 px-0 text-[color:var(--color-ink)]/70 text-[9px] [&_span:first-child]:flex [&_span:first-child]:items-center [&_span:first-child]:[gap:7px] [&_span:last-child]:tracking-[1px] max-[550px]:gap-3 max-[550px]:leading-[1.5] max-[550px]:[&_span:last-child]:hidden">
      <span>
        <ShieldCheck size={14} /> Perception dashboard · Flight control operates
        independently
      </span>
      <span>VIGIL / GROUND STATION v1.0</span>
    </footer>
  );
}
