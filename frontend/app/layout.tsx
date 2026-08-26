import type { Metadata } from 'next';
import { Inter, IBM_Plex_Mono, Special_Elite } from 'next/font/google';
import './styles.css';

const body = Inter({ subsets: ['latin'], variable: '--font-body', display: 'swap' });
const mono = IBM_Plex_Mono({ subsets: ['latin'], weight: ['400', '500', '600'], variable: '--font-mono', display: 'swap' });
const display = Special_Elite({ subsets: ['latin'], weight: '400', variable: '--font-display', display: 'swap' });

export const metadata: Metadata = {
  title: 'ShadowIntel',
  description: 'Investigation intelligence workspace',
};

// Runs before paint so the stored theme (or system preference) applies
// immediately, instead of flashing dark mode and then switching.
const THEME_INIT = `(function(){try{var t=localStorage.getItem('shadowintel-theme');if(t!=='light'&&t!=='dark'){t=window.matchMedia('(prefers-color-scheme: light)').matches?'light':'dark';}document.documentElement.dataset.theme=t;}catch(e){document.documentElement.dataset.theme='dark';}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning className={`${body.variable} ${mono.variable} ${display.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}