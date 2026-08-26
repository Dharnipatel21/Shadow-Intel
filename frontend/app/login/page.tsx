'use client';

import Link from 'next/link';
import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';

const API = process.env.NEXT_PUBLIC_API_URL ?? '';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const response = await fetch(API + '/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) });
      const data = await response.json();
      if (response.status === 403) { router.replace('/verify?email=' + encodeURIComponent(email)); return; }
      if (response.status === 401) { setError('Incorrect email or password.'); return; }
      if (!response.ok) throw new Error(data.detail || 'Unable to sign in.');
      localStorage.setItem('shadowintel-token', data.token); router.replace('/dashboard');
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Unable to sign in.'); } finally { setBusy(false); }
  }
  async function continueWithGoogle() {
    setBusy(true); setError('');
    try {
      const response = await fetch(API + '/api/auth/google/login'); const data = await response.json();
      if (!response.ok || !data.url) throw new Error(data.detail || 'Unable to start Google sign-in.');
      window.location.assign(data.url);
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Unable to start Google sign-in.'); setBusy(false); }
  }
  return <main className="auth-shell"><div className="auth-wrap"><div className="brand auth-brand"><span className="mark">SHADOW<span>INTEL</span></span><small>INVESTIGATION WORKSPACE</small></div><section className="card auth-card"><p className="eyebrow">SECURE ACCESS</p><h1>Sign in</h1><p>Continue to your investigation workspace.</p><form className="auth-form" onSubmit={signIn}><label>Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required /></label><label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required /></label>{error && <p className="notice auth-error" role="alert">{error}</p>}<button type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button></form><div className="auth-divider">OR</div><button className="auth-google" type="button" onClick={continueWithGoogle} disabled={busy}>Continue with Google</button><p className="auth-link">New to ShadowIntel? <Link href="/signup">Create an account</Link></p></section><p className="disclaimer auth-disclaimer">ShadowIntel assists investigation and evidence analysis. It does not determine guilt, criminality, or legal responsibility.</p></div></main>;
}