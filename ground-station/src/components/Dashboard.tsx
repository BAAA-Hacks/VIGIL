"use client";
import { useState } from "react";
import type { ThermalPalette } from "../types/vigil";
import { useVigilFeed } from "../hooks/useVigilFeed";
import { Sidebar } from "./dashboard/Sidebar";
import { DashboardHeader } from "./dashboard/DashboardHeader";
import { DashboardTitle } from "./dashboard/DashboardTitle";
import { MetricsGrid } from "./dashboard/MetricsGrid";
import { ThermalPanel } from "./dashboard/ThermalPanel";
import { DetectionInsight } from "./dashboard/DetectionInsight";
import { FeedControls } from "./dashboard/FeedControls";
import { DashboardFooter } from "./dashboard/DashboardFooter";

export default function Dashboard() {
  const feed = useVigilFeed();
  const [palette, setPalette] = useState<ThermalPalette>("iron");
  const [overlay, setOverlay] = useState(true);
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="py-0 px-[38px] max-w-[1600px] w-full m-auto max-[1100px]:py-0 max-[1100px]:px-6 max-[550px]:py-0 max-[550px]:px-4">
        <DashboardHeader demo={feed.demo} />
        <DashboardTitle onStartDemo={feed.startDemo} />
        <MetricsGrid feed={feed} />
        <div className=" grid [grid-template-columns:minmax(0,_1fr)_302px] gap-5 max-[1100px]:[grid-template-columns:minmax(0,_1fr)_270px] max-[850px]:grid-cols-1">
          <ThermalPanel
            feed={feed}
            palette={palette}
            onPaletteChange={setPalette}
            overlay={overlay}
            onOverlayChange={setOverlay}
            expanded={expanded}
            onExpandedChange={setExpanded}
          />
          <div className="flex flex-col gap-5 max-[850px]:grid max-[850px]:grid-cols-2 max-[550px]:grid-cols-1">
            <DetectionInsight feed={feed} />
            <FeedControls feed={feed} />
          </div>
        </div>
        <DashboardFooter />
      </main>
    </div>
  );
}
