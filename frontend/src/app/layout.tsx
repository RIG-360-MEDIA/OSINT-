import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "RIG SURVEILLANCE",
  description: "Personal Intelligence Platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-black text-white min-h-screen">{children}</body>
    </html>
  );
}
