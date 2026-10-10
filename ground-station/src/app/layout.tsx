import type { Metadata } from "next";
import type { ReactNode } from "react";
import "leaflet/dist/leaflet.css";
import "./globals.css";
export const metadata: Metadata = {
  title: "VIGIL · Ground Station",
  icons: { icon: "/icon.svg" },
  description: "Thermal awareness and human detection dashboard",
};
export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://server.arcgisonline.com" />
      </head>
      <body className="m-0 bg-[var(--color-paper)] [font-family:Arial,Helvetica,sans-serif] text-[color:var(--color-ink)] [font-synthesis:none]">
        <a href="#mission-content" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[2000] focus:rounded focus:bg-[var(--color-paper)] focus:p-3">Skip to dashboard</a>
        {children}
      </body>
    </html>
  );
}
