import "./globals.css";
import { Fraunces, Inter, JetBrains_Mono } from "next/font/google";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const fraunces = Fraunces({ subsets: ["latin"], variable: "--font-fraunces" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jbmono" });

export const metadata = { title: "Atlas · Personal Operating System" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className={`${inter.variable} ${fraunces.variable} ${mono.variable}`}>
      <head>
        {/* anti-flash: aplica el tema guardado antes de pintar */}
        <script
          dangerouslySetInnerHTML={{
            __html: "document.documentElement.dataset.theme=localStorage.getItem('atlas-theme')||'dark'",
          }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
