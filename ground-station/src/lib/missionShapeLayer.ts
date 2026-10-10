import type * as Leaflet from "leaflet";
import { shapeCoordinates, type PathShape } from "./missionPath";

interface ShapeDrawing {
  outline: Leaflet.Circle | Leaflet.Polyline | Leaflet.Polygon;
  points: Leaflet.Marker[];
}

/** Reuses paths and waypoint markers while previewing edits independently of React. */
export class MissionShapeLayer {
  private readonly group: Leaflet.LayerGroup;
  private readonly handles: Leaflet.LayerGroup;
  private readonly route: Leaflet.Polyline;
  private readonly drawings = new Map<string, ShapeDrawing>();
  private readonly ink: string;
  private readonly blue: string;
  private shapes: PathShape[] = [];
  private selectedId: string | null = null;
  private animation: number | null = null;

  constructor(
    private readonly L: typeof Leaflet,
    private readonly map: Leaflet.Map,
    private readonly change: (shape: PathShape) => void,
    private readonly select: (id: string) => void,
  ) {
    this.group = L.layerGroup().addTo(map);
    this.handles = L.layerGroup().addTo(map);
    const style = getComputedStyle(map.getContainer());
    this.ink = style.getPropertyValue("--color-ink").trim();
    this.blue = style.getPropertyValue("--color-blue").trim();
    this.route = L.polyline([], {
      color: this.ink,
      weight: 2,
      dashArray: "5 5",
      interactive: false,
    }).addTo(this.group);
  }

  render(shapes: PathShape[], selectedId: string | null, editing: boolean) {
    this.cancelPreview();
    this.shapes = shapes;
    this.selectedId = selectedId;
    const active = new Set(shapes.map((shape) => shape.id));
    for (const [id, drawing] of this.drawings) {
      if (!active.has(id)) {
        this.group.removeLayer(drawing.outline);
        drawing.points.forEach((point) => this.group.removeLayer(point));
        this.drawings.delete(id);
      }
    }
    let number = 0;
    for (const shape of shapes) {
      if (!this.drawings.has(shape.id)) this.createDrawing(shape, number);
      number += shapeCoordinates(shape).length;
      this.updateDrawing(shape);
    }
    this.updateRoute();
    // Only committed edits rebuild handles; drag previews keep the grabbed marker alive.
    this.handles.clearLayers();
    const selected = shapes.find((shape) => shape.id === selectedId);
    if (selected && editing) this.addHandles(selected);
  }

  private createDrawing(shape: PathShape, number: number) {
    const coordinates = shapeCoordinates(shape).map((p): [number, number] => [
      p.latitude,
      p.longitude,
    ]);
    const options = { color: this.ink, fillColor: this.blue };
    const outline =
      shape.kind === "circle"
        ? this.L.circle([shape.latitude, shape.longitude], {
            ...options,
            radius: shape.sizeM,
          })
        : shape.kind === "line"
          ? this.L.polyline(coordinates, options)
          : this.L.polygon(coordinates, options);
    outline.on("click", () => this.select(shape.id)).addTo(this.group);
    const points = coordinates.map((point) => {
      const label = document.createElement("span");
      label.className =
        "grid size-5 place-items-center rounded-[2px] border border-[color:var(--color-ink)] bg-[var(--color-ink)] text-[10px] font-bold text-[color:var(--color-paper)]";
      label.textContent = String(++number);
      return this.L.marker(point, {
        interactive: false,
        keyboard: false,
        icon: this.L.divIcon({
          html: label,
          className: "mission-waypoint",
          iconSize: [20, 20],
          iconAnchor: [10, 10],
        }),
      }).addTo(this.group);
    });
    this.drawings.set(shape.id, { outline, points });
  }

  private updateDrawing(shape: PathShape) {
    const drawing = this.drawings.get(shape.id);
    if (!drawing) return;
    const coordinates = shapeCoordinates(shape).map((p): [number, number] => [
      p.latitude,
      p.longitude,
    ]);
    if (drawing.outline instanceof this.L.Circle) {
      drawing.outline
        .setLatLng([shape.latitude, shape.longitude])
        .setRadius(shape.sizeM);
    } else drawing.outline.setLatLngs(coordinates);
    drawing.outline.setStyle({
      weight: shape.id === this.selectedId ? 2 : 1,
      fillOpacity: shape.id === this.selectedId ? 0.2 : 0.08,
    });
    drawing.points.forEach((marker, index) => {
      marker.setLatLng(coordinates[index]);
      // Renumber after an earlier shape is removed, without rebuilding marker elements.
      const preceding = this.shapes
        .slice(
          0,
          this.shapes.findIndex((s) => s.id === shape.id),
        )
        .reduce((sum, s) => sum + shapeCoordinates(s).length, 0);
      const label = marker.getElement()?.firstElementChild;
      if (label) label.textContent = String(preceding + index + 1);
    });
  }

  private updateRoute() {
    this.route.setLatLngs(
      this.shapes
        .flatMap(shapeCoordinates)
        .map((p): [number, number] => [p.latitude, p.longitude]),
    );
  }

  private preview(shape: PathShape, afterDraw: () => void) {
    this.shapes = this.shapes.map((old) => (old.id === shape.id ? shape : old));
    // Pointer events can arrive faster than display frames. Draw the latest position once per frame.
    this.cancelPreview();
    this.animation = requestAnimationFrame(() => {
      this.animation = null;
      this.updateDrawing(shape);
      this.updateRoute();
      afterDraw();
    });
  }

  private cancelPreview() {
    if (this.animation !== null) cancelAnimationFrame(this.animation);
    this.animation = null;
  }

  private addHandles(shape: PathShape) {
    const create = (point: [number, number], title: string, symbol: string) => {
      const label = document.createElement("span");
      label.className =
        "grid size-7 place-items-center rounded-[3px] border-2 border-[color:var(--color-ink)] bg-[var(--color-paper)] text-sm font-bold text-[color:var(--color-ink)]";
      label.textContent = symbol;
      return this.L.marker(point, {
        draggable: true,
        title,
        zIndexOffset: 1200,
        icon: this.L.divIcon({
          html: label,
          className: "mission-handle",
          iconSize: [28, 28],
          iconAnchor: [14, 14],
        }),
      }).addTo(this.handles);
    };
    const corner = (draft: PathShape): [number, number] => {
      const point = shapeCoordinates({ ...draft, kind: "square" })[1];
      return [point.latitude, point.longitude];
    };
    const move = create(
      [shape.latitude, shape.longitude],
      "Drag to move shape",
      "✥",
    );
    const resize = create(corner(shape), "Drag to resize shape", "↔");
    const moved = () => {
      const p = move.getLatLng();
      return { ...shape, latitude: p.lat, longitude: p.lng };
    };
    const resized = () => {
      const p = resize.getLatLng();
      const north = (((p.lat - shape.latitude) * Math.PI) / 180) * 6371000;
      const east =
        (((p.lng - shape.longitude) * Math.PI) / 180) *
        6371000 *
        Math.cos((shape.latitude * Math.PI) / 180);
      return {
        ...shape,
        sizeM: Math.max(
          2,
          Math.min(500, Math.max(Math.abs(north), Math.abs(east))),
        ),
      };
    };
    move.on("drag", () => {
      const draft = moved();
      this.preview(draft, () => resize.setLatLng(corner(draft)));
    });
    resize.on("drag", () => this.preview(resized(), () => {}));
    const commit = (draft: PathShape) => {
      this.cancelPreview();
      this.shapes = this.shapes.map((old) =>
        old.id === draft.id ? draft : old,
      );
      this.updateDrawing(draft);
      this.updateRoute();
      this.change(draft);
    };
    move.on("dragend", () => commit(moved()));
    resize.on("dragend", () => commit(resized()));
  }

  dispose() {
    this.cancelPreview();
    this.group.remove();
    this.handles.remove();
    this.drawings.clear();
  }
}
