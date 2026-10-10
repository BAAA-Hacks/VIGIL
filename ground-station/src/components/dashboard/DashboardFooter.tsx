import { ShieldCheck } from "lucide-react";
export function DashboardFooter() {
  return (
    <footer>
      <span>
        <ShieldCheck size={14} /> Perception dashboard · Flight control operates
        independently
      </span>
      <span>VIGIL / GROUND STATION v1.0</span>
    </footer>
  );
}
