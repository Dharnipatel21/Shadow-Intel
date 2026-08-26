'use client';

import Link from 'next/link';
import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';

const API = process.env.NEXT_PUBLIC_API_URL ?? '';

export default function SignupPage() {
  const router = useRouter();
  const [name, setName] = useState(''); const [email, setEmail] = useState(''); const [password, setPassword] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  async function signUp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const response = await fetch(API + '/api/auth/signup', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, email, password }) }); const data = await response.json();
      if (response.status === 409) { setError('An account already exists for this email.'); return; }
      if (!response.ok) throw new Error(data.detail || 'Unable to create account.');
      router.replace('/verify?email=' + encodeURIComponent(email));
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Unable to create account.'); } finally { setBusy(false); }
  }
  return <main className="auth-shell"><div className="auth-wrap"><div className="brand auth-brand"><span className="mark">SHADOW<span>INTEL</span></span><small>INVESTIGATION WORKSPACE</small></div><section className="card auth-card"><p className="eyebrow">NEW INVESTIGATOR</p><h1>Create account</h1><p>Set up secure access to ShadowIntel.</p><form className="auth-form" onSubmit={signUp}><label>Name<input value={name} onChange={(event) => setName(event.target.value)} autoComplete="name" required /></label><label>Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required /></label><label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" required /></label>{error && <p className="notice auth-error" role="alert">{error}</p>}<button type="submit" disabled={busy}>{busy ? 'Creating account…' : 'Create account'}</button></form><p className="auth-link">Already have an account? <Link href="/login">Sign in</Link></p></section><p className="disclaimer auth-disclaimer">ShadowIntel assists investigation and evidence analysis. It does not determine guilt, criminality, or legal responsibility.</p></div></main>;
}