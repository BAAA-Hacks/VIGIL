"use client";
import { useEffect, useRef, useState } from "react";
import type { Map as LeafletMap, Marker } from "leaflet";
import { TEMPERATURE_STATUS } from "../../lib/temperatureStatus";
import type { PinData } from "../../types/mission";
interface PersonMapProps {
  pins: PinData[];
  focusedPin: PinData | null;
  focusRevision: number;
  onSelectPerson: (pin: PinData) => void;
  compact: boolean;
}
export function PersonMap({
  pins,
  focusedPin,
  focusRevision,
  onSelectPerson,
  compact,
}: PersonMapProps) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const markers = useRef(new Map<string, Marker>());
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
      const map = L.map(host, { scrollWheelZoom: false }).setView(
        [34.053, -118.243],
        16,
      );
      mapRef.current = map;
      L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
        {
          attribution:
            "Tiles &copy; Esri &mdash; Sources: Esri, HERE, Garmin, USGS, Intermap, INCREMENT P, NRCan, METI, Esri Japan, Esri China (Hong Kong), OpenStreetMap contributors, GIS User Community",
          maxZoom: 19,
        },
      ).addTo(map);
      for (const pin of pins) {
        const label = document.createElement("span");
        label.className = `person-map-marker ${TEMPERATURE_STATUS[pin.status].markerClass}`;
        label.textContent = pin.id;
        const marker = L.marker([pin.latitude, pin.longitude], {
          icon: L.divIcon({
            html: label,
            className: "person-map-icon",
            iconSize: [28, 28],
            iconAnchor: [14, 14],
          }),
          title: `${pin.name}: ${pin.coords} · ${TEMPERATURE_STATUS[pin.status].label}`,
          keyboard: true,
        }).addTo(map);
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
        marker.on("click", () => selectRef.current(pin));
        markers.current.set(pin.id, marker);
      }
      if (pins.length)
        map.fitBounds(
          L.latLngBounds(pins.map((pin) => [pin.latitude, pin.longitude])),
          { padding: [40, 40], maxZoom: 16 },
        );
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
    };
  }, [pins]);
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !focusedPin) return;
    map.setView([focusedPin.latitude, focusedPin.longitude], 17, {
      animate: !window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    });
    markers.current.get(focusedPin.id)?.openPopup();
  }, [ready, focusedPin, focusRevision]);
  useEffect(() => {
    mapRef.current?.invalidateSize({ pan: false });
  }, [compact]);
  return (
    <div className="person-map-container">
      <div
        ref={container}
        className="person-map-canvas"
        aria-label="Map of detected person coordinates"
      />
      {error && (
        <p className="person-map-error">
          Map could not load. Person coordinates remain available in the list.
        </p>
      )}
    </div>
  );
}
