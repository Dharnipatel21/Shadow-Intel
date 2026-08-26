'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function AuthCallbackPage() {
  const router = useRouter();
  useEffect(() => { const token = new URLSearchParams(window.location.search).get('token'); if (token) { localStorage.setItem('shadowintel-token', token); router.replace('/dashboard'); return; } router.replace('/login'); }, [router]);
  return <main className="auth-shell"><p className="loading">Completing secure sign-in…</p></main>;
}
