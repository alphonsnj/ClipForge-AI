import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ClipForge AI — Find the moment worth sharing",
  description:
    "Turn long conversations into thoughtful, reviewable short-form clips. Your voice stays yours; every cut stays in your hands.",
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
