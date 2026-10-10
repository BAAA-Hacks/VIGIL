import { ChevronRight } from "lucide-react";
export function DashboardHeader({ demo }: { demo: boolean }) {
  return (
    <header>
      <div className="breadcrumb">
        Workspace <ChevronRight size={14} /> Ground station
      </div>
      <div className="header-right">
        <span className="demo-tag">
          {demo ? "SIMULATION MODE" : "LIVE INPUT MODE"}
        </span>
        <span className="avatar">OP</span>
      </div>
    </header>
  );
}
