import { Play } from "lucide-react";
export function DashboardTitle({ onStartDemo }: { onStartDemo: () => void }) {
  return (
    <div className="title-row">
      <div>
        <div className="eyebrow">VISUAL INTELLIGENCE & GEOLOCATION</div>
        <h1>
          Eyes on the field<span>.</span>
        </h1>
        <p>Thermal awareness. Clear decisions.</p>
      </div>
      <button
        className="inline-flex items-center justify-center gap-2 rounded-md bg-[#86ebc6] px-[18px] py-3 text-xs font-bold text-[#10261e] hover:bg-[#a4f4d7] max-[550px]:p-2.5 max-[550px]:text-[10px]"
        onClick={onStartDemo}
      >
        <Play size={16} /> Start demo
      </button>
    </div>
  );
}
