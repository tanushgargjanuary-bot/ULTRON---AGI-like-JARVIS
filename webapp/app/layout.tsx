import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ULTRON Web",
  description: "A web interface for the ULTRON assistant.",
  applicationName: "ULTRON Web",
  robots: { index: false, follow: false }
};

export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="en"><body>{children}</body></html>;
}
