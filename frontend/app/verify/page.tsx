'use client';

import Link from 'next/link';
import { FormEvent, Suspense, useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

const API = process.env.NEXT_PUBLIC_API_URL ?? '';

function VerifyForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [resending, setResending] = useState(false);

  useEffect(() => { const e = params.get('email'); if (e) setEmail(e); }, [params]);

  async function verify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('');
    try {
      const response = await fetch(API + '/api/auth/verify-otp', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, code }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Invalid or expired code.');
      localStorage.setItem('shadowintel-token', data.token); router.replace('/dashboard');
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Invalid or expired code.'); } finally { setBusy(false); }
  }

  async function resend() {
    setResending(true); setError(''); setNotice('');
    try {
      const response = await fetch(API + '/api/auth/resend-otp', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Unable to resend code.');
      setNotice('A new code has been sent to your email.');
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Unable to resend code.'); } finally { setResending(false); }
  }

  return <main className="auth-shell"><div className="auth-wrap"><div className="brand auth-brand"><span className="mark">SHADOW<span>INTEL</span></span><small>INVESTIGATION WORKSPACE</small></div><section className="card auth-card"><p className="eyebrow">EMAIL VERIFICATION</p><h1>Enter your code</h1><p>We sent a 6-digit verification code to {email || 'your email'}.</p><form className="auth-form" onSubmit={verify}><label>Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required /></label><label>Verification code<input value={code} onChange={(event) => setCode(event.target.value)} maxLength={6} inputMode="numeric" autoComplete="one-time-code" required /></label>{error && <p className="notice auth-error" role="alert">{error}</p>}{notice && <p className="notice">{notice}</p>}<button type="submit" disabled={busy}>{busy ? 'Verifying…' : 'Verify account'}</button></form><button className="auth-google" type="button" onClick={resend} disabled={resending}>{resending ? 'Resending…' : 'Resend code'}</button><p className="auth-link">Wrong email? <Link href="/signup">Start over</Link></p></section><p className="disclaimer auth-disclaimer">ShadowIntel assists investigation and evidence analysis. It does not determine guilt, criminality, or legal responsibility.</p></div></main>;
}

export default function VerifyPage() {
  return <Suspense fallback={<main className="auth-shell"><div className="loading">Loading verification…</div></main>}><VerifyForm /></Suspense>;
}
