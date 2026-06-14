import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "World Cup Prediction Tool",
  description: "DeepSeek/GPT assisted football prediction methodology dashboard.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <nav className="top-nav" aria-label="Primary navigation">
          <a href="/">Prediction</a>
          <a href="/predictions">History</a>
          <a href="/sources">Sources</a>
          <a href="/backtests">Backtests</a>
          <a href="/weights">Weights</a>
          <a href="/reports">Reports</a>
          <a href="/methodology">Methodology</a>
        </nav>
        {children}
      </body>
    </html>
  );
}
