import { Radar, ScanLine, ShieldCheck } from "lucide-react";
export function Sidebar() {
  return (
    <aside>
      <a className="brand" href="#">
        <Radar />
        <span>
          VIGIL<span className="brand-dot">.</span>
        </span>
      </a>
      <div className="workspace">GROUND OPERATIONS</div>
      <div className="nav-item">
        <ScanLine size={19} /> Overview <span>01</span>
      </div>
      <div className="aside-bottom">
        <ShieldCheck size={20} />
        <div>
          Operator station<small>Perception & monitoring</small>
        </div>
      </div>
    </aside>
  );
}
