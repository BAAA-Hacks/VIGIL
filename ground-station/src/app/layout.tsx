import type { Metadata } from "next";
import type { ReactNode } from "react";
import "leaflet/dist/leaflet.css";
import "./globals.css";
import "./mission.css";
export const metadata: Metadata = {
  title: "VIGIL · Ground Station",
  description: "Thermal awareness and human detection dashboard",
};
export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
