import { Radar, ScanLine, ShieldCheck } from "lucide-react";
export function Sidebar() {
  return (
    <aside className="w-[212px] shrink-0 border-r border-[color:var(--color-ink)]/25 py-[30px] px-[22px] relative bg-[var(--color-paper)] max-[1100px]:w-[170px] max-[1100px]:px-[15px] max-[1100px]:py-[25px] max-[850px]:w-[70px] max-[850px]:px-[15px] max-[850px]:py-[25px] max-[550px]:hidden">
      <a
        className="[&:focus-visible]:[outline:2px_solid_var(--color-ink)] [&:focus-visible]:[outline-offset:4px]  flex items-center gap-2.5 text-[color:var(--color-ink)] no-underline [font-family:'Space_Grotesk',_sans-serif] text-[27px] font-bold tracking-[2px] [&_svg]:text-[color:var(--color-ink)] [&_svg]:w-[29px] [&_svg]:h-[29px] max-[850px]:[&_>_span]:hidden"
        href="#"
      >
        <Radar />
        <span>
          VIGIL
          <span className=" text-[color:var(--color-ink)]">.</span>
        </span>
      </a>
      <div className=" text-[9px] tracking-[1.7px] text-[color:var(--color-ink)]/70 mt-[54px] mb-[17px] max-[850px]:hidden">
        GROUND OPERATIONS
      </div>
      <div className=" flex items-center gap-2.5 border border-[color:var(--color-ink)]/25 bg-[var(--color-ink)]/8 text-[color:var(--color-ink)] p-3 rounded-[7px] text-[13px] [&_span]:ml-auto [&_span]:text-[10px] [&_span]:[opacity:0.6] max-[850px]:[&_span]:hidden max-[850px]:hidden">
        <ScanLine size={19} /> Overview <span>01</span>
      </div>
      <div className=" absolute bottom-7 flex gap-2.5 items-center text-[color:var(--color-ink)]/70 text-[11px] [&_small]:block [&_small]:text-[color:var(--color-ink)]/70 [&_small]:mt-[5px] [&_small]:text-[9px] max-[850px]:hidden">
        <ShieldCheck size={20} />
        <div>
          Operator station<small>Perception & monitoring</small>
        </div>
      </div>
    </aside>
  );
}
