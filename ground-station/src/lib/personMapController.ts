import type * as Leaflet from "leaflet";
import type { PinData } from "../types/mission";
import type { VehicleTelemetry } from "../types/telemetry";
import type { MapView } from "../components/mission/MapViewSelect";
import { validFix } from "./geolocation";
import { enableSmoothMapZoom } from "./smoothMapZoom";
import { TEMPERATURE_STATUS } from "./temperatureStatus";

// Safari has no requestIdleCallback.
const idle = typeof requestIdleCallback === "function";
const requestIdle = (task: () => void) =>
  idle
    ? requestIdleCallback(task, { timeout: 3000 })
    : window.setTimeout(task, 1000);
const cancelIdle = (id: number) =>
  idle ? cancelIdleCallback(id) : window.clearTimeout(id);

const tileUrl = (view: MapView) => {
  const service = {
    satellite: "World_Imagery",
    topographic: "World_Topo_Map",
    street: "World_Street_Map",
  }[view];
  return `https://server.arcgisonline.com/ArcGIS/rest/services/${service}/MapServer/tile/{z}/{y}/{x}`;
};

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

interface PersonMarker {
  marker: Leaflet.Marker;
  label: HTMLSpanElement;
  pin: PinData;
  contentKey: string;
}

/** Owns Leaflet resources; React supplies snapshots without recreating markers. */
export class PersonMapController {
  private readonly map: Leaflet.Map;
  private tiles: Leaflet.TileLayer;
  private sharpenTimer = 0;
  private readonly observer: ResizeObserver;
  private readonly stopZoom: () => void;
  private readonly people = new Map<string, PersonMarker>();
  private drone: Leaflet.Marker | null = null;
  private droneContent = "";
  private fittedSource = "";
  private focusRevision = -1;
  private layer: MapView;

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
      zoomSnap: 0,
      zoomDelta: 0.5,
    }).setView([34.053, -118.243], 16);
    this.stopZoom = enableSmoothMapZoom(this.map);
    // Set the initial bounds before requesting tiles, and request only the chosen layer.
    this.update(pins, drone);
    this.tiles = L.tileLayer(tileUrl(layer), this.tileOptions(false)).addTo(
      this.map,
    );
    // Standard tiles paint first; sharp tiles replace them once the browser is idle,
    // so high-DPI screens get crisp maps without delaying the first paint.
    if (L.Browser.retina)
      this.tiles.once("load", () => {
        this.sharpenTimer = requestIdle(() => this.sharpen());
      });
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
      const text = pin.displayLabel ?? pin.id;
      entry.label.textContent = text;
      entry.label.className = `grid size-7 place-items-center rounded-full border-2 text-xs font-bold shadow-[0_1px_3px_color-mix(in_srgb,_var(--color-ink)_40%,_transparent)] [font-family:Arial,sans-serif] ${TEMPERATURE_STATUS[pin.status].markerClass}`;
      // The accessible name starts with the visible label (WCAG 2.5.3).
      const title = `${text} · ${pin.name}: ${pin.coords} · ${TEMPERATURE_STATUS[pin.status].label}`;
      entry.marker.getElement()?.setAttribute("title", title);
      entry.marker.getElement()?.setAttribute("aria-label", title);
      const key = JSON.stringify([pin.name, pin.coords, pin.temp, pin.status]);
      if (entry.contentKey !== key) {
        const content = popup(
          pin.name,
          pin.coords,
          `${pin.temp} · ${TEMPERATURE_STATUS[pin.status].label}`,
        );
        if (entry.marker.getPopup()) entry.marker.setPopupContent(content);
        else entry.marker.bindPopup(content);
        entry.contentKey = key;
      }
    }
    const fixed = drone && validFix(drone) ? drone : null;
    this.updateDrone(fixed);
    const source = pins[0]?.locationNote ? "live" : "fixture";
    if (pins.length && source !== this.fittedSource) {
      this.fittedSource = source;
      const points: [number, number][] = pins.map((pin) => [
        pin.latitude,
        pin.longitude,
      ]);
      if (fixed) points.push([fixed.lat!, fixed.lon!]);
      // A low hover sees people 15-80 m away; pins only separate near tile zoom 19.
      this.map.fitBounds(this.L.latLngBounds(points), {
        ...this.fitPadding(),
        maxZoom: 19,
      });
    } else if (!pins.length && fixed && !this.fittedSource) {
      this.map.setView([fixed.lat!, fixed.lon!], 16);
      this.fittedSource = "drone";
    }
  }

  private updateDrone(drone: VehicleTelemetry | null) {
    if (!drone) {
      this.drone?.remove();
      this.drone = null;
      this.droneContent = "";
      return;
    }
    if (!this.drone) {
      const label = document.createElement("span");
      label.className =
        "grid size-8 place-items-center rounded-[4px] border-2 border-[color:var(--color-ink)] bg-[var(--color-blue)] text-xs font-bold text-[color:var(--color-ink)]";
      label.textContent = "D";
      this.drone = this.L.marker([drone.lat!, drone.lon!], {
        icon: this.L.divIcon({
          html: label,
          className: "drone-map-icon",
          iconSize: [32, 32],
          iconAnchor: [16, 16],
        }),
        title: "Drone",
        // Below the person pins: people are the targets and must stay clickable.
        zIndexOffset: -1000,
      }).addTo(this.map);
      this.drone.getElement()?.setAttribute("aria-label", "D · Drone");
    }
    const current = this.drone.getLatLng();
    if (current.lat !== drone.lat || current.lng !== drone.lon)
      this.drone.setLatLng([drone.lat!, drone.lon!]);
    const coordinates = `${drone.lat!.toFixed(6)}, ${drone.lon!.toFixed(6)}`;
    const altitude =
      drone.altitude_m === null
        ? "Altitude unavailable"
        : `${drone.altitude_m.toFixed(1)} m above sea level`;
    const key = `${coordinates}|${altitude}`;
    if (key !== this.droneContent) {
      const content = popup("Drone", coordinates, altitude);
      if (this.drone.getPopup()) this.drone.setPopupContent(content);
      else this.drone.bindPopup(content);
      this.droneContent = key;
    }
  }

  private tileOptions(retina: boolean): Leaflet.TileLayerOptions {
    return {
      attribution:
        "Tiles &copy; Esri &mdash; Sources: Esri, HERE, Garmin, USGS, Intermap, INCREMENT P, NRCan, METI, Esri Japan, Esri China (Hong Kong), OpenStreetMap contributors, GIS User Community",
      // detectRetina requests one zoom level deeper and lowers maxZoom by one;
      // offset both so zoom 19 stays usable.
      detectRetina: retina,
      maxZoom: retina ? 20 : 19,
      maxNativeZoom: retina ? 18 : 19,
    };
  }

  private sharpen() {
    const sharp = this.L.tileLayer(tileUrl(this.layer), this.tileOptions(true));
    sharp.once("load", () => {
      this.tiles.remove();
      this.tiles = sharp;
    });
    sharp.addTo(this.map);
  }

  /** Keeps fitted pins clear of the attribution and of the corner inset pane. */
  private fitPadding() {
    const host = this.map.getContainer();
    const size = this.map.getSize();
    // The attribution wraps onto several lines on phones.
    let right = 40,
      bottom = 72;
    const inset = host
      .closest("[data-viewers]")
      ?.querySelector<HTMLElement>("[data-inset]");
    if (inset && !inset.contains(host)) {
      const box = inset.getBoundingClientRect();
      const keptHeight = size.y - 40 - (box.height + 24),
        keptWidth = size.x - 40 - (box.width + 24);
      // Reserve whichever side costs less of the map.
      if (keptHeight / size.y >= keptWidth / size.x) {
        if (keptHeight >= 120) bottom = Math.max(bottom, box.height + 24);
      } else if (keptWidth >= 120) right = box.width + 24;
    }
    return {
      paddingTopLeft: [40, 40] as [number, number],
      paddingBottomRight: [right, bottom] as [number, number],
    };
  }

  focus(pin: PinData | null, revision: number) {
    if (!pin || revision === this.focusRevision) return;
    this.focusRevision = revision;
    // Center on the person; never zoom out, which would re-stack nearby pins.
    this.map.setView(
      [pin.latitude, pin.longitude],
      Math.max(17, this.map.getZoom()),
      {
        animate: !window.matchMedia("(prefers-reduced-motion: reduce)").matches,
      },
    );
    this.people.get(pin.id)?.marker.openPopup();
  }
  setLayer(layer: MapView) {
    if (layer === this.layer) return;
    this.layer = layer;
    // A pending sharp layer reads this.layer when it is created, and replaces the
    // current one on load; update every tile layer on the map.
    this.map.eachLayer((item) => {
      if (item instanceof this.L.TileLayer) item.setUrl(tileUrl(layer));
    });
  }
  resize() {
    this.map.invalidateSize({ pan: false });
  }
  dispose() {
    cancelIdle(this.sharpenTimer);
    this.observer.disconnect();
    this.stopZoom();
    this.map.remove();
    this.people.clear();
  }
}
