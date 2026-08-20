import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "homepod-agent",
  description: "Local-first home automation dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}