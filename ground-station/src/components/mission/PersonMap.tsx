"use client";
import { useEffect, useRef, useState } from "react";
import type { Map as LeafletMap, Marker, TileLayer } from "leaflet";
import type { VehicleTelemetry } from "../../types/telemetry";
import { validFix } from "../../lib/geolocation";
import { TEMPERATURE_STATUS } from "../../lib/temperatureStatus";
import type { MapView } from "./MapViewSelect";
import type { PinData } from "../../types/mission";
interface PersonMapProps {
  drone?: VehicleTelemetry | null;
  pins: PinData[];
  focusedPin: PinData | null;
  focusRevision: number;
  onSelectPerson: (pin: PinData) => void;
  compact: boolean;
  layer: MapView;
}
export function PersonMap({
  pins,
  drone,
  focusedPin,
  focusRevision,
  onSelectPerson,
  compact,
  layer,
}: PersonMapProps) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const droneMarker = useRef<Marker | null>(null);
  const tileRef = useRef<TileLayer | null>(null);
  const markers = useRef(new Map<string, Marker>());
  const fittedSource = useRef("");
  const lastFocusRevision = useRef(-1);
  const selectRef = useRef(onSelectPerson);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState(false);
  useEffect(() => {
    selectRef.current = onSelectPerson;
  }, [onSelectPerson]);
  useEffect(() => {
    let disposed = false;
    let observer: ResizeObserver | undefined;
    const host = container.current;
    if (!host) return;
    async function initialize() {
      const L = await import("leaflet");
      if (disposed || !host) return;
      const map = L.map(host, {
        scrollWheelZoom: true,
        touchZoom: true,
        zoomSnap: 0.25,
        zoomDelta: 0.5,
        wheelPxPerZoomLevel: 120,
      }).setView([34.053, -118.243], 16);
      mapRef.current = map;
      tileRef.current = L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
        {
          attribution:
            "Tiles &copy; Esri &mdash; Sources: Esri, HERE, Garmin, USGS, Intermap, INCREMENT P, NRCan, METI, Esri Japan, Esri China (Hong Kong), OpenStreetMap contributors, GIS User Community",
          maxZoom: 19,
        },
      ).addTo(map);
      observer = new ResizeObserver(() => map.invalidateSize({ pan: false }));
      observer.observe(host);
      setReady(true);
    }
    initialize().catch(() => {
      if (!disposed) setError(true);
    });
    return () => {
      disposed = true;
      observer?.disconnect();
      mapRef.current?.remove();
      mapRef.current = null;
      markers.current.clear();
      droneMarker.current = null;
    };
  }, []);
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    let disposed = false;
    import("leaflet").then((L) => {
      if (disposed) return;
      const active = new Set(pins.map((pin) => pin.id));
      for (const [id, marker] of markers.current) {
        if (!active.has(id)) {
          marker.remove();
          markers.current.delete(id);
        }
      }
      const source = pins[0]?.locationNote ? "live" : "fixture";
      for (const pin of pins) {
        const label = document.createElement("span");
        label.className = `grid size-7 place-items-center rounded-full border-2 text-xs font-bold shadow-[0_1px_3px_color-mix(in_srgb,_var(--color-ink)_40%,_transparent)] [font-family:Arial,sans-serif] ${TEMPERATURE_STATUS[pin.status].markerClass}`;
        label.textContent = pin.displayLabel ?? pin.id;
        const marker =
          markers.current.get(pin.id) ??
          L.marker([pin.latitude, pin.longitude], {
            icon: L.divIcon({
              html: label,
              className: "person-map-icon",
              iconSize: [28, 28],
              iconAnchor: [14, 14],
            }),
            title: `${pin.name}: ${pin.coords} · ${TEMPERATURE_STATUS[pin.status].label}`,
            keyboard: true,
          }).addTo(map);
        marker.setLatLng([pin.latitude, pin.longitude]);
        marker.setIcon(
          L.divIcon({
            html: label,
            className: "person-map-icon",
            iconSize: [28, 28],
            iconAnchor: [14, 14],
          }),
        );
        const content = document.createElement("div");
        const name = document.createElement("strong");
        name.textContent = pin.name;
        content.append(
          name,
          document.createElement("br"),
          document.createTextNode(pin.coords),
          document.createElement("br"),
          document.createTextNode(
            `${pin.temp} · ${TEMPERATURE_STATUS[pin.status].label}`,
          ),
        );
        marker.bindPopup(content);
        marker.off("click");
        marker.on("click", () => selectRef.current(pin));
        markers.current.set(pin.id, marker);
      }
      if (pins.length && fittedSource.current !== source) {
        fittedSource.current = source;
        map.fitBounds(
          L.latLngBounds([
            ...pins.map((pin): [number, number] => [
              pin.latitude,
              pin.longitude,
            ]),
            ...(drone && validFix(drone)
              ? [[drone.lat!, drone.lon!] as [number, number]]
              : []),
          ]),
          { padding: [40, 40], maxZoom: 16 },
        );
      }
    });
    return () => {
      disposed = true;
    };
  }, [pins, ready, drone]);
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    if (!drone || !validFix(drone)) {
      droneMarker.current?.remove();
      droneMarker.current = null;
      return;
    }
    let disposed = false;
    import("leaflet").then((L) => {
      if (disposed) return;
      const label = document.createElement("span");
      label.className =
        "grid size-8 place-items-center rounded-[4px] border-2 border-[color:var(--color-ink)] bg-[var(--color-blue)] text-xs font-bold text-[color:var(--color-ink)]";
      label.textContent = "D";
      const marker =
        droneMarker.current ??
        L.marker([drone.lat!, drone.lon!], {
          icon: L.divIcon({
            html: label,
            className: "drone-map-icon",
            iconSize: [32, 32],
            iconAnchor: [16, 16],
          }),
          title: "Drone",
          zIndexOffset: 1000,
        }).addTo(map);
      marker.setLatLng([drone.lat!, drone.lon!]);
      const content = document.createElement("div");
      const name = document.createElement("strong");
      name.textContent = "Drone";
      content.append(
        name,
        document.createElement("br"),
        document.createTextNode(
          drone.lat!.toFixed(6) + ", " + drone.lon!.toFixed(6),
        ),
        document.createElement("br"),
        document.createTextNode(
          drone.altitude_m === null
            ? "Altitude unavailable"
            : drone.altitude_m.toFixed(1) + " m above sea level",
        ),
      );
      marker.bindPopup(content);
      droneMarker.current = marker;
      if (!pins.length && !fittedSource.current) {
        map.setView([drone.lat!, drone.lon!], 16);
        fittedSource.current = "drone";
      }
    });
    return () => {
      disposed = true;
    };
  }, [ready, drone, pins.length]);
  useEffect(() => {
    const map = mapRef.current;
    if (
      !ready ||
      !map ||
      !focusedPin ||
      lastFocusRevision.current === focusRevision
    )
      return;
    lastFocusRevision.current = focusRevision;
    map.setView([focusedPin.latitude, focusedPin.longitude], 17, {
      animate: !window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    });
    markers.current.get(focusedPin.id)?.openPopup();
  }, [ready, focusedPin, focusRevision]);
  useEffect(() => {
    mapRef.current?.invalidateSize({ pan: false });
  }, [compact]);
  useEffect(() => {
    const service =
      layer === "satellite"
        ? "World_Imagery"
        : layer === "topographic"
          ? "World_Topo_Map"
          : "World_Street_Map";
    tileRef.current?.setUrl(
      `https://server.arcgisonline.com/ArcGIS/rest/services/${service}/MapServer/tile/{z}/{y}/{x}`,
    );
  }, [layer, ready]);
  return (
    <div className="relative size-full [&_.leaflet-control-attribution]:max-w-[80%] [&_.leaflet-control-attribution]:text-[9px] [&_.leaflet-control-attribution_a]:text-[color:var(--color-ink)]">
      <div
        ref={container}
        className="size-full bg-[var(--color-paper)]"
        aria-label="Map of detected person coordinates"
      />
      {error && (
        <p className="leading-relaxed absolute inset-x-2.5 top-1/2 z-[1000] bg-[var(--color-paper)] p-3 text-xs leading-relaxed text-[color:var(--color-ink)]/70">
          Map could not load. Person coordinates remain available in the list.
        </p>
      )}
    </div>
  );
}
