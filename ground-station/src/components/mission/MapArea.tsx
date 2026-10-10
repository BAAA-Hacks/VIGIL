"use client";
import { useState } from "react";
import { ArrowUpRight, ArrowLeftRight } from "lucide-react";
import { ThermalImage } from "../dashboard/ThermalImage";
import { PersonMap } from "./PersonMap";
import type { PinData } from "../../types/mission";
interface MapAreaProps {
  pins: PinData[];
  focusedPin: PinData | null;
  focusRevision: number;
  onSelectPerson: (pin: PinData) => void;
}
export function MapArea(props: MapAreaProps) {
  const [thermalPrimary, setThermalPrimary] = useState(false);
  const swap = () => setThermalPrimary((value) => !value);
  return (
    <section
      className={`mission-map mission-viewer ${thermalPrimary ? "thermal-primary" : ""}`}
      aria-label="Map and thermal camera"
    >
      <div className="mission-map-heading">
        <span>
          {thermalPrimary ? "Thermal camera · Simulated" : "Search area"}
        </span>
        <button
          className="view-swap-button"
          onClick={swap}
          aria-label="Swap map and thermal camera"
        >
          <ArrowLeftRight size={13} /> Swap views
        </button>
      </div>
      <div
        className={`viewer-pane ${thermalPrimary ? "viewer-inset" : "viewer-main"}`}
      >
        <PersonMap {...props} compact={thermalPrimary} />
        {thermalPrimary && (
          <button
            className="inset-promote map-promote"
            onClick={swap}
            aria-label="Expand map"
          >
            <ArrowUpRight size={13} /> Map
          </button>
        )}
      </div>
      <div
        className={`viewer-pane thermal-pane ${thermalPrimary ? "viewer-main" : "viewer-inset"}`}
      >
        <ThermalImage
          frame={null}
          detection={null}
          demo
          palette="white"
          hasPerson
        />
        {!thermalPrimary && (
          <button
            className="inset-promote thermal-promote"
            onClick={swap}
            aria-label="Expand thermal camera"
          >
            <span>Thermal · Simulated</span>
            <ArrowUpRight size={13} />
          </button>
        )}
      </div>
    </section>
  );
}
