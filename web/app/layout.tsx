import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "Unsplash desk",
  description: "Review locations, tags, and profile visibility before anything is written to Unsplash.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a className="skip" href="#content">
          Skip to the sheet
        </a>
        <header className="mast">
          <div>
            <p className="eyebrow">Xuedi · @liuxuedi</p>
            <a className="wordmark" href="/studio">
              Unsplash desk
            </a>
          </div>
          <form action="/api/logout" method="post">
            <button className="text-button" type="submit">
              Lock
            </button>
          </form>
        </header>
        {children}
        <footer className="foot">
          Nothing is written until you press Apply. This desk fills places and tags in code. Camera GPS, phone tracks, and the optional model stay on the <code>upw</code> command.
        </footer>
      </body>
    </html>
  );
}
