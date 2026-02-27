import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";

export const metadata: Metadata = {
  title: "Incident Copilot",
  description: "AI-powered incident analysis for on-call engineers",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-cream min-h-screen">
        <Sidebar />
        <main className="md:ml-64 min-h-screen">
          {children}
        </main>
      </body>
    </html>
  );
}
