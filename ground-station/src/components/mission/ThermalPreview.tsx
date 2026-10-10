import { ThermalImage } from "../dashboard/ThermalImage";
export function ThermalPreview() {
  return (
    <div className="absolute bottom-4 right-4 w-[220px] overflow-hidden rounded-[3px] border border-[color:var(--color-ink)]/25 bg-[var(--color-paper)] max-[600px]:bottom-2.5 max-[600px]:right-2.5 max-[600px]:w-[180px]">
      <div className="flex items-center justify-between border-b border-[color:var(--color-ink)]/25 px-2.5 py-[9px] text-[10px]">
        <span>Thermal camera</span>
      </div>
      <ThermalImage
        frame={null}
        detection={null}
        demo
        palette="white"
        presentation="preview"
        hasPerson
      />
    </div>
  );
}
