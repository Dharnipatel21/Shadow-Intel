'use client';
import { useEffect, useState } from 'react';

type Theme = 'dark' | 'light';
const STORAGE_KEY = 'shadowintel-theme';

export function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setThemeState] = useState<Theme>('dark');
  useEffect(() => {
    const current = (document.documentElement.dataset.theme as Theme) || 'dark';
    setThemeState(current);
  }, []);
  const setTheme = (t: Theme) => {
    document.documentElement.dataset.theme = t;
    try {
      localStorage.setItem(STORAGE_KEY, t);
    } catch {
      /* localStorage unavailable, theme still applies for this session */
    }
    setThemeState(t);
  };
  return [theme, setTheme];
}

export default function ThemeToggle({ theme, onChange }: { theme: Theme; onChange: (t: Theme) => void }) {
  return (
    <div className="theme-toggle" role="group" aria-label="Colour theme">
      <button className={theme === 'dark' ? 'active' : ''} onClick={() => onChange('dark')} aria-pressed={theme === 'dark'}>
        DARK
      </button>
      <button className={theme === 'light' ? 'active' : ''} onClick={() => onChange('light')} aria-pressed={theme === 'light'}>
        LIGHT
      </button>
    </div>
  );
}