import type { Map as LeafletMap, Point } from "leaflet";

/** Continuous wheel/trackpad zoom using Leaflet's public, cursor-anchored API. */
export function enableSmoothMapZoom(map: LeafletMap): () => void {
  const host = map.getContainer();
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let target = map.getZoom();
  let anchor: Point | null = null;
  let animation = 0;
  let previousTime = 0;
  let applying = false;
  let disposed = false;

  const cancel = () => {
    cancelAnimationFrame(animation);
    animation = 0;
    previousTime = 0;
    target = map.getZoom();
  };
  const apply = (zoom: number) => {
    if (!anchor) return;
    applying = true;
    try {
      map.setZoomAround(anchor, zoom, { animate: false });
    } finally {
      applying = false;
    }
  };
  const step = (time: number) => {
    if (disposed) return;
    const elapsed = previousTime ? Math.min(64, time - previousTime) : 16;
    previousTime = time;
    const current = map.getZoom();
    const remaining = target - current;
    if (Math.abs(remaining) < 0.002) {
      apply(target);
      animation = 0;
      previousTime = 0;
      return;
    }
    apply(current + remaining * (1 - Math.exp(-elapsed / 65)));
    animation = requestAnimationFrame(step);
  };
  const wheel = (event: WheelEvent) => {
    if (!event.deltaY || !Number.isFinite(event.deltaY)) return;
    if (
      event.target instanceof Element &&
      event.target.closest(".leaflet-control, input, select, textarea")
    )
      return;
    event.preventDefault();
    event.stopPropagation();
    if (!animation) {
      map.stop();
      target = map.getZoom();
    }
    anchor = map.mouseEventToContainerPoint(event);
    const unit =
      event.deltaMode === 1
        ? 16
        : event.deltaMode === 2
          ? host.clientHeight
          : 1;
    const pixels = Math.max(-120, Math.min(120, event.deltaY * unit));
    // Use gentle wheel increments; small trackpad deltas accumulate continuously.
    target = Math.max(
      map.getMinZoom(),
      Math.min(map.getMaxZoom(), target - pixels / 400),
    );
    if (reducedMotion.matches) {
      cancelAnimationFrame(animation);
      animation = 0;
      previousTime = 0;
      apply(target);
    } else if (!animation) animation = requestAnimationFrame(step);
  };
  const externalMove = () => {
    if (!applying) cancel();
  };
  const motionChange = () => {
    if (reducedMotion.matches) {
      apply(target);
      cancel();
    }
  };
  host.addEventListener("wheel", wheel, { passive: false });
  map.on("movestart", externalMove);
  reducedMotion.addEventListener("change", motionChange);
  return () => {
    disposed = true;
    cancel();
    host.removeEventListener("wheel", wheel);
    map.off("movestart", externalMove);
    reducedMotion.removeEventListener("change", motionChange);
  };
}
