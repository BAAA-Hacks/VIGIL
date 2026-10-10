"use client";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ShapeToolbar } from "./ShapeToolbar";
import { MissionPathPanel } from "./MissionPathPanel";
import { useMissionPlanner } from "../../hooks/useMissionPlanner";
import { SHAPE_POINTS, type PathShapeKind } from "../../lib/missionPath";
import { PersonMapController } from "../../lib/personMapController";
import type { VehicleTelemetry } from "../../types/telemetry";
import type { MapView } from "./MapViewSelect";
import type { PinData } from "../../types/mission";

interface PersonMapProps {
  drone?: VehicleTelemetry | null;
  pins: PinData[];
  focusedPin: PinData | null;
  focusRevision: number;
  onSelectPerson: (pin: PinData) => void;
  onAddPerson: (latitude: number, longitude: number) => void;
  compact: boolean;
  layer: MapView;
}

export function PersonMap(props: PersonMapProps) {
  const container = useRef<HTMLDivElement>(null);
  const controller = useRef<PersonMapController | null>(null);
  const latest = useRef(props);
  const [error, setError] = useState(false);
  const [toolbarHost, setToolbarHost] = useState<HTMLElement | null>(null);
  const planner = useMissionPlanner();
  const plannerRef = useRef(planner);
  useEffect(() => {
    plannerRef.current = planner;
  });
  useEffect(() => {
    controller.current?.setMission(
      planner.shapes,
      planner.selectedId,
      !props.compact && !planner.sending,
      (shape) => plannerRef.current.update(shape),
      (id) => plannerRef.current.select(id),
    );
  }, [planner.shapes, planner.selectedId, planner.sending, props.compact]);
  function addShape(kind: PathShapeKind, clientX?: number, clientY?: number) {
    const placement = controller.current?.placement(clientX, clientY);
    if (placement)
      planner.add(
        kind,
        placement.latitude,
        placement.longitude,
        placement.sizeM,
      );
  }

  useEffect(() => {
    latest.current = props;
    const map = controller.current;
    if (!map) return;
    map.update(props.pins, props.drone);
    // Markers are updated synchronously before opening the selected popup.
    map.focus(props.focusedPin, props.focusRevision);
    map.setLayer(props.layer);
  }, [props]);

  useEffect(() => {
    let disposed = false;
    const host = container.current;
    if (!host) return;
    setToolbarHost(
      host.closest("section")?.querySelector<HTMLElement>("[data-map-tools]") ??
        null,
    );
    import("leaflet")
      .then((L) => {
        if (disposed) return;
        const current = latest.current;
        const map = new PersonMapController(
          L,
          host,
          current.layer,
          (pin) => latest.current.onSelectPerson(pin),
          current.pins,
          current.drone,
        );
        controller.current = map;
        const plan = plannerRef.current;
        map.setMission(
          plan.shapes,
          plan.selectedId,
          !current.compact && !plan.sending,
          (shape) => plannerRef.current.update(shape),
          (id) => plannerRef.current.select(id),
        );
        map.focus(current.focusedPin, current.focusRevision);
      })
      .catch(() => {
        if (!disposed) setError(true);
      });
    return () => {
      disposed = true;
      controller.current?.dispose();
      controller.current = null;
    };
  }, []);

  useEffect(() => {
    controller.current?.resize();
  }, [props.compact]);

  return (
    <div
      onDragOver={(event) => {
        if (
          !props.compact &&
          (event.dataTransfer.types.includes("application/x-vigil-shape") ||
            event.dataTransfer.types.includes("application/x-vigil-person"))
        ) {
          event.preventDefault();
          event.dataTransfer.dropEffect = "copy";
        }
      }}
      onDrop={(event) => {
        if (props.compact || !container.current?.contains(event.target as Node))
          return;
        if (event.dataTransfer.types.includes("application/x-vigil-person")) {
          event.preventDefault();
          const point = controller.current?.placement(
            event.clientX,
            event.clientY,
          );
          if (point) props.onAddPerson(point.latitude, point.longitude);
          return;
        }
        if (planner.sending) return;
        const kind = event.dataTransfer.getData("application/x-vigil-shape");
        if (Object.hasOwn(SHAPE_POINTS, kind)) {
          event.preventDefault();
          addShape(kind as PathShapeKind, event.clientX, event.clientY);
        }
      }}
      className="relative size-full has-[details[open]]:grid has-[details[open]]:grid-cols-[288px_minmax(0,1fr)] max-[600px]:has-[details[open]]:grid-cols-1 max-[600px]:has-[details[open]]:grid-rows-[minmax(0,1fr)_minmax(180px,1fr)] [&_.leaflet-control-attribution]:max-w-[calc(100%-16px)] [&_.leaflet-control-attribution]:whitespace-nowrap [&_.leaflet-control-attribution]:overflow-x-auto [&_.leaflet-control-attribution]:[scrollbar-width:none] [&_.leaflet-control-attribution::-webkit-scrollbar]:hidden [&_.leaflet-control-attribution]:text-[9px] [&_.leaflet-control-attribution_a]:text-[color:var(--color-ink)]"
    >
      <div
        ref={container}
        className="size-full min-h-0 min-w-0 bg-[var(--color-paper)]"
        aria-label="Map of detected person coordinates"
      />
      {!props.compact && !error && (
        <>
          {toolbarHost &&
            createPortal(
              <ShapeToolbar
                disabled={planner.sending}
                onAdd={addShape}
                onAddPerson={() => {
                  const point = controller.current?.placement();
                  if (point) props.onAddPerson(point.latitude, point.longitude);
                }}
              />,
              toolbarHost,
            )}
          <MissionPathPanel planner={planner} />
        </>
      )}
      {error && (
        <p
          role="status"
          className="absolute inset-x-2.5 top-1/2 z-[1000] bg-[var(--color-paper)] p-3 text-xs leading-relaxed text-[color:var(--color-ink)]/70"
        >
          Map could not load. Person coordinates remain available in the list.
        </p>
      )}
    </div>
  );
}
