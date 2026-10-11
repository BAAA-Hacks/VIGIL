import type * as Leaflet from "leaflet";
import type { PinData } from "../types/mission";
import type { VehicleTelemetry } from "../types/telemetry";
import type { MapView } from "../components/mission/MapViewSelect";
import { validFix } from "./geolocation";
import { markerHeading } from "./droneHeading";
import { enableSmoothMapZoom } from "./smoothMapZoom";
import { MissionShapeLayer } from "./missionShapeLayer";
import type { PathShape } from "./missionPath";
import { TEMPERATURE_STATUS } from "./temperatureStatus";

const tileUrl = (view: MapView) => `/api/map-tiles/${view}/{z}/{x}/{y}`;

function popup(name: string, coordinates: string, detail: string) {
  const content = document.createElement("div");
  const heading = document.createElement("strong");
  heading.textContent = name;
  content.append(
    heading,
    document.createElement("br"),
    document.createTextNode(coordinates),
    document.createElement("br"),
    document.createTextNode(detail),
  );
  return content;
}

/** Trail points closer than this to the previous one are skipped (GPS jitter while hovering). */
const TRAIL_MIN_STEP_M = 1;
const TRAIL_MAX_POINTS = 5000;
/** A drone absent this long starts a new trail when it comes back (a new flight). */
const TRAIL_RESET_AFTER_MS = 60_000;

interface PersonMarker {
  marker: Leaflet.Marker;
  label: HTMLSpanElement;
  pin: PinData;
  contentKey: string;
}

/** Owns Leaflet resources; React supplies snapshots without recreating markers. */
export class PersonMapController {
  private readonly map: Leaflet.Map;
  private readonly tiles: Leaflet.TileLayer;
  private readonly observer: ResizeObserver;
  private readonly stopZoom: () => void;
  private readonly people = new Map<string, PersonMarker>();
  private drone: Leaflet.Marker | null = null;
  private droneArrow: HTMLSpanElement | null = null;
  private droneContent = "";
  private trail: Leaflet.Polyline | null = null;
  private trailPoints: [number, number][] = [];
  private home: Leaflet.Marker | null = null;
  private droneLastSeen = 0;
  private lastCourse: number | null = null;
  private fittedSource = "";
  private focusRevision = -1;
  private layer: MapView;
  private missionLayer: MissionShapeLayer | null = null;

  constructor(
    private readonly L: typeof Leaflet,
    host: HTMLElement,
    layer: MapView,
    private readonly select: (pin: PinData) => void,
    pins: PinData[],
    drone?: VehicleTelemetry | null,
  ) {
    this.layer = layer;
    this.map = L.map(host, {
      scrollWheelZoom: false,
      touchZoom: true,
      zoomControl: false,
      zoomSnap: 0,
      zoomDelta: 0.5,
    }).setView([28.601667, -81.200556], 16);
    L.control.zoom({ position: "bottomleft" }).addTo(this.map);
    this.stopZoom = enableSmoothMapZoom(this.map);
    // Set the initial bounds before requesting tiles, and request only the chosen layer.
    this.update(pins, drone);
    this.tiles = L.tileLayer(tileUrl(layer), {
      attribution:
        "Tiles &copy; Esri &mdash; Sources: Esri, HERE, Garmin, USGS, Intermap, INCREMENT P, NRCan, METI, Esri Japan, Esri China (Hong Kong), OpenStreetMap contributors, GIS User Community",
      maxZoom: 19,
    }).addTo(this.map);
    const credits = this.map.attributionControl.getContainer();
    if (credits) {
      credits.tabIndex = 0;
      credits.setAttribute(
        "aria-label",
        "Map sources; scroll horizontally to read all credits",
      );
    }
    this.observer = new ResizeObserver(() => this.resize());
    this.observer.observe(host);
  }

  update(pins: PinData[], drone?: VehicleTelemetry | null) {
    const active = new Set(pins.map((pin) => pin.id));
    for (const [id, entry] of this.people) {
      if (!active.has(id)) {
        entry.marker.remove();
        this.people.delete(id);
      }
    }
    for (const pin of pins) {
      let entry = this.people.get(pin.id);
      if (!entry) {
        const label = document.createElement("span");
        const marker = this.L.marker([pin.latitude, pin.longitude], {
          icon: this.L.divIcon({
            html: label,
            className: "person-map-icon",
            iconSize: [28, 28],
            iconAnchor: [14, 14],
          }),
          keyboard: true,
        }).addTo(this.map);
        entry = { marker, label, pin, contentKey: "" };
        this.people.set(pin.id, entry);
        const item = entry;
        // Keep Leaflet's popup listener and read the latest pin on selection.
        marker.on("click", () => this.select(item.pin));
      }
      entry.pin = pin;
      const current = entry.marker.getLatLng();
      if (current.lat !== pin.latitude || current.lng !== pin.longitude)
        entry.marker.setLatLng([pin.latitude, pin.longitude]);
      entry.label.textContent = pin.displayLabel ?? pin.id;
      entry.label.className = `grid size-7 place-items-center rounded-full border-2 text-xs font-bold shadow-[0_1px_3px_color-mix(in_srgb,_var(--color-ink)_40%,_transparent)] [font-family:Arial,sans-serif] ${TEMPERATURE_STATUS[pin.status].markerClass}`;
      const detail = pin.manual
        ? pin.groundElevationM !== undefined
          ? `${pin.groundElevationM.toFixed(1)} m ground elevation`
          : pin.elevationState === "loading"
            ? "Ground elevation looking up…"
            : "Ground elevation unavailable"
        : `${pin.temp} · ${TEMPERATURE_STATUS[pin.status].label}`;
      const title = `${pin.name}: ${pin.coords} · ${detail}`;
      entry.marker.getElement()?.setAttribute("title", title);
      entry.marker.getElement()?.setAttribute("aria-label", title);
      const key = JSON.stringify([pin.name, pin.coords, detail]);
      if (entry.contentKey !== key) {
        const content = popup(pin.name, pin.coords, detail);
        if (entry.marker.getPopup()) entry.marker.setPopupContent(content);
        else entry.marker.bindPopup(content);
        entry.contentKey = key;
      }
    }
    const fixed = drone && validFix(drone) ? drone : null;
    this.updateDrone(fixed);
    const sourcePin = pins.find((pin) => !pin.manual);
    const source = sourcePin
      ? sourcePin.locationNote
        ? "live"
        : "fixture"
      : this.fittedSource;
    if (source === "fixture" && !fixed && !this.fittedSource)
      this.fittedSource = source;
    if (pins.length && source !== this.fittedSource) {
      this.fittedSource = source;
      const points: [number, number][] = pins.map((pin) => [
        pin.latitude,
        pin.longitude,
      ]);
      if (fixed) points.push([fixed.lat!, fixed.lon!]);
      this.map.fitBounds(this.L.latLngBounds(points), {
        padding: [40, 40],
        maxZoom: 16,
      });
    } else if (!pins.length && fixed && !this.fittedSource) {
      this.map.setView([fixed.lat!, fixed.lon!], 16);
      this.fittedSource = "drone";
    }
  }

  /** Flight trail, home point and travel direction; the trail outlives brief link dropouts. */
  private updateTrack(drone: VehicleTelemetry) {
    const now = Date.now();
    if (this.droneLastSeen && now - this.droneLastSeen > TRAIL_RESET_AFTER_MS) {
      this.trailPoints = [];
      this.lastCourse = null;
    }
    this.droneLastSeen = now;
    const point: [number, number] = [drone.lat!, drone.lon!];
    const last = this.trailPoints.at(-1);
    if (!last || this.map.distance(last, point) >= TRAIL_MIN_STEP_M) {
      this.trailPoints.push(point);
      if (this.trailPoints.length > TRAIL_MAX_POINTS) this.trailPoints.shift();
    }
    if (!this.trail)
      this.trail = this.L.polyline([], {
        color: "#1f6feb",
        weight: 3,
        opacity: 0.8,
        dashArray: "6 6",
        interactive: false,
      }).addTo(this.map);
    this.trail.setLatLngs(this.trailPoints);
    const home = drone.home;
    if (home && Number.isFinite(home.lat) && Number.isFinite(home.lon)) {
      if (!this.home) {
        const label = document.createElement("span");
        label.className =
          "grid size-6 place-items-center rounded-full border-2 border-[color:var(--color-ink)] bg-[var(--color-paper)] text-[10px] font-bold text-[color:var(--color-ink)]";
        label.textContent = "H";
        this.home = this.L.marker([home.lat, home.lon], {
          icon: this.L.divIcon({
            html: label,
            className: "drone-home-icon",
            iconSize: [24, 24],
            iconAnchor: [12, 12],
          }),
          title: "Home (take-off point)",
          zIndexOffset: 900,
        }).addTo(this.map);
      } else this.home.setLatLng([home.lat, home.lon]);
    }
    // Magnetometer heading (nose direction) when calibrated, else GPS course (see droneHeading.ts).
    const heading = markerHeading(drone, this.lastCourse);
    this.lastCourse = heading.lastCourse;
    if (this.droneArrow) {
      this.droneArrow.hidden = heading.deg === null;
      if (heading.deg !== null) {
        this.droneArrow.style.transform = `rotate(${heading.deg}deg)`;
        this.droneArrow.style.opacity = heading.current ? "1" : "0.4";
        this.droneArrow.title =
          heading.source === "nose"
            ? "Heading (magnetometer)"
            : "Direction of travel (GPS course)";
      }
    }
  }

  private updateDrone(drone: VehicleTelemetry | null) {
    if (!drone) {
      this.drone?.remove();
      this.drone = null;
      this.droneArrow = null;
      this.droneContent = "";
      return;
    }
    if (!this.drone) {
      const label = document.createElement("span");
      label.className =
        "relative grid size-8 place-items-center rounded-[4px] border-2 border-[color:var(--color-ink)] bg-[var(--color-blue)] text-xs font-bold text-[color:var(--color-ink)]";
      label.textContent = "D";
      // Heading pointer (magnetometer nose direction, or GPS course), rotated about the marker centre.
      const arrow = document.createElement("span");
      arrow.className =
        "pointer-events-none absolute inset-[-14px] [transform-origin:center]";
      arrow.innerHTML =
        '<span class="absolute left-1/2 top-0 -translate-x-1/2 border-x-[6px] border-b-[10px] border-x-transparent border-b-[color:var(--color-ink)]"></span>';
      arrow.hidden = true;
      label.append(arrow);
      this.droneArrow = arrow;
      this.drone = this.L.marker([drone.lat!, drone.lon!], {
        icon: this.L.divIcon({
          html: label,
          className: "drone-map-icon",
          iconSize: [32, 32],
          iconAnchor: [16, 16],
        }),
        title: "Drone",
        zIndexOffset: 1000,
      }).addTo(this.map);
    }
    const current = this.drone.getLatLng();
    if (current.lat !== drone.lat || current.lng !== drone.lon)
      this.drone.setLatLng([drone.lat!, drone.lon!]);
    this.updateTrack(drone);
    const coordinates = `${drone.lat!.toFixed(6)}, ${drone.lon!.toFixed(6)}`;
    const details = [
      drone.altitude_m === null
        ? "Altitude unavailable"
        : `${drone.altitude_m.toFixed(1)} m above home`,
      ...(drone.speed_ms !== undefined && drone.speed_ms !== null
        ? [`${drone.speed_ms.toFixed(1)} m/s`]
        : []),
      ...(drone.satellites !== null ? [`${drone.satellites} satellites`] : []),
    ].join(" · ");
    const key = `${coordinates}|${details}`;
    if (key !== this.droneContent) {
      const content = popup("Drone", coordinates, details);
      if (this.drone.getPopup()) this.drone.setPopupContent(content);
      else this.drone.bindPopup(content);
      this.droneContent = key;
    }
  }

  focus(pin: PinData | null, revision: number) {
    if (!pin || revision === this.focusRevision) return;
    this.focusRevision = revision;
    this.map.setView([pin.latitude, pin.longitude], 17, {
      animate: !window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    });
    this.people.get(pin.id)?.marker.openPopup();
  }
  setLayer(layer: MapView) {
    if (layer === this.layer) return;
    this.layer = layer;
    // Leaflet 1.9 redraw uses the fractional map zoom in tile URLs. Reattaching
    // runs its normal integer tile-zoom setup without changing the viewport.
    this.tiles.remove();
    this.tiles.setUrl(tileUrl(layer), true).addTo(this.map);
  }
  placement(clientX?: number, clientY?: number) {
    const rect = this.map.getContainer().getBoundingClientRect();
    const point =
      clientX === undefined || clientY === undefined
        ? this.map.latLngToContainerPoint(this.map.getCenter())
        : this.L.point(clientX - rect.left, clientY - rect.top);
    const center = this.map.containerPointToLatLng(point);
    const edge = this.map.containerPointToLatLng(point.add([45, 0]));
    return {
      latitude: center.lat,
      longitude: center.lng,
      sizeM: Math.max(2, Math.min(500, this.map.distance(center, edge))),
    };
  }
  setMission(
    shapes: PathShape[],
    selectedId: string | null,
    editing: boolean,
    change: (shape: PathShape) => void,
    select: (id: string) => void,
  ) {
    if (!this.missionLayer && shapes.length)
      this.missionLayer = new MissionShapeLayer(
        this.L,
        this.map,
        change,
        select,
      );
    this.missionLayer?.render(shapes, selectedId, editing);
  }
  async openOfflineMission() {
    const response = await fetch("/api/offline-mission");
    const mission = await response.json();
    const bounds = mission?.bounds;
    if (
      !bounds ||
      ![bounds.south, bounds.north, bounds.west, bounds.east].every(
        Number.isFinite,
      )
    )
      throw new Error("No prepared mission area found.");
    this.map.fitBounds(
      [
        [bounds.south, bounds.west],
        [bounds.north, bounds.east],
      ],
      { padding: [16, 16], animate: false },
    );
  }
  async saveOfflineArea(progress: (done: number, total: number) => void) {
    const bounds = this.map.getBounds();
    const baseZoom = Math.floor(this.map.getZoom());
    const urls: string[] = [];
    for (
      let z = Math.max(0, baseZoom - 1);
      z <= Math.min(19, baseZoom + 2);
      z++
    ) {
      const nw = this.map
        .project(bounds.getNorthWest(), z)
        .divideBy(256)
        .floor();
      const se = this.map
        .project(bounds.getSouthEast(), z)
        .divideBy(256)
        .floor();
      for (let x = nw.x; x <= se.x; x++)
        for (let y = nw.y; y <= se.y; y++) {
          const wrappedX = ((x % 2 ** z) + 2 ** z) % 2 ** z;
          if (y >= 0 && y < 2 ** z)
            for (const layer of ["topographic", "street", "satellite"] as const)
              urls.push(`/api/map-tiles/${layer}/${z}/${wrappedX}/${y}`);
          if (urls.length > 1500)
            throw new Error("Area too large. Zoom in before saving.");
        }
    }
    let done = 0,
      failed = 0;
    progress(done, urls.length);
    for (let start = 0; start < urls.length; start += 4) {
      await Promise.all(
        urls.slice(start, start + 4).map(async (url) => {
          try {
            const response = await fetch(url);
            if (!response.ok) failed++;
            else await response.arrayBuffer();
          } catch {
            failed++;
          }
          progress(++done, urls.length);
        }),
      );
    }
    if (failed)
      throw new Error(
        `${urls.length - failed}/${urls.length} tiles saved. Connect to internet and retry for complete coverage.`,
      );
  }
  resize() {
    this.map.invalidateSize({
      pan: true,
      animate: false,
      debounceMoveend: true,
    });
  }
  dispose() {
    this.observer.disconnect();
    this.stopZoom();
    this.missionLayer?.dispose();
    this.map.remove();
    this.people.clear();
  }
}
