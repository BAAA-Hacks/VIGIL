import type { Metadata } from "next";
import type { ReactNode } from "react";
import "leaflet/dist/leaflet.css";
import "./globals.css";
export const metadata: Metadata = {
  title: "VIGIL · Ground Station",
  description: "Thermal awareness and human detection dashboard",
};
export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body className="m-0 bg-[var(--color-paper)] [font-family:Arial,Helvetica,sans-serif] text-[color:var(--color-ink)] [font-synthesis:none]">
        {children}
      </body>
    </html>
  );
}
