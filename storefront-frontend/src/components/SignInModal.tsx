'use client';

import Script from 'next/script';
import { useEffect, useRef, useState, useTransition } from 'react';

import {
  signInWithGoogleCredential,
  signInWithWidgetToken,
} from '@/lib/auth/actions';

import styles from './SignInModal.module.css';

const DEFAULT_OTP_LENGTH = 6;
const RESEND_SECONDS = 60;
/** Long enough to solve a visible hCaptcha challenge, short of hanging forever. */
const SEND_TIMEOUT_MS = 60_000;
const COUNTRY_CODE = '91';

const WIDGET_ID = process.env.NEXT_PUBLIC_MSG91_WIDGET_ID;
const TOKEN_AUTH = process.env.NEXT_PUBLIC_MSG91_TOKEN_AUTH;

const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;

/**
 * MSG91's widget is driven from our own markup; Google Identity Services
 * renders its sign-in button into the same modal.
 */
declare global {
  interface Window {
    initSendOTP?: (config: Record<string, unknown>) => void;
    sendOtp?: (
      identifier: string,
      success: (data: unknown) => void,
      failure: (error: unknown) => void,
    ) => void;
    verifyOtp?: (
      otp: string,
      success: (data: unknown) => void,
      failure: (error: unknown) => void,
    ) => void;
    getWidgetData?: () => { otpLength?: number } | undefined;
    retryOtp?: (
      channel: string | null,
      success: (data: unknown) => void,
      failure: (error: unknown) => void,
    ) => void;
    google?: {
      accounts: {
        id: {
          initialize: (options: {
            client_id: string;
            ux_mode: 'popup';
            callback: (response: { credential: string }) => void;
          }) => void;
          renderButton: (
            element: HTMLElement,
            options: { theme: string; size: string; text: string; width: number },
          ) => void;
        };
      };
    };
  }
}

/** MSG91 returns the token on `message`, and errors in a few shapes. */
function readToken(data: unknown): string {
  if (typeof data === 'string') return data;
  if (data && typeof data === 'object' && 'message' in data) {
    const message = (data as { message: unknown }).message;
    if (typeof message === 'string') return message;
  }
  return '';
}

function readError(error: unknown, fallback: string): string {
  if (typeof error === 'string') return error;
  if (error && typeof error === 'object' && 'message' in error) {
    const message = (error as { message: unknown }).message;
    if (typeof message === 'string') return message;
  }
  return fallback;
}

/**
 * Phone OTP and Google sign-in, over whatever page the shopper is on.
 *
 * Both of the OTP steps stay inside the modal because the MSG91 widget holds
 * the pending code in the browser. `next` is where the session action
 * redirects once the account is signed in -- by default the page underneath.
 */
export default function SignInModal({ next, onClose }: { next: string; onClose: () => void }) {
  const [phone, setPhone] = useState('');
  const [identifier, setIdentifier] = useState('');
  const [otpLength, setOtpLength] = useState(DEFAULT_OTP_LENGTH);
  const [code, setCode] = useState('');
  const [step, setStep] = useState<'phone' | 'code'>('phone');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [googleError, setGoogleError] = useState('');
  const [seconds, setSeconds] = useState(0);
  const [widgetReady, setWidgetReady] = useState(false);
  const [, startTransition] = useTransition();

  const googleButtonRef = useRef<HTMLDivElement>(null);
  const identityRef = useRef<HTMLInputElement>(null);
  const otpRef = useRef<HTMLInputElement>(null);
  const sendWatchdogRef = useRef<number | undefined>(undefined);

  const configured = Boolean(WIDGET_ID && TOKEN_AUTH);
  const googleConfigured = Boolean(GOOGLE_CLIENT_ID);

  useEffect(() => {
    if (seconds <= 0) return;
    const timer = setTimeout(() => setSeconds(s => s - 1), 1000);
    return () => clearTimeout(timer);
  }, [seconds]);

  useEffect(() => {
    if (step === 'code') otpRef.current?.focus();
    else identityRef.current?.focus();
  }, [step]);

  // Escape closes, and the page underneath stops scrolling while open.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    document.addEventListener('keydown', onKeyDown);

    return () => {
      document.body.style.overflow = overflow;
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [onClose]);

  useEffect(() => () => window.clearTimeout(sendWatchdogRef.current), []);

  const initializeGoogle = () => {
    const button = googleButtonRef.current;
    if (!GOOGLE_CLIENT_ID || !window.google || !button || button.dataset.initialized) return;

    button.dataset.initialized = 'true';
    window.google.accounts.id.initialize({
      client_id: GOOGLE_CLIENT_ID,
      ux_mode: 'popup',
      callback: response => {
        if (!response.credential) {
          setGoogleError('Google sign-in did not return a credential. Try again.');
          return;
        }

        setGoogleError('');
        setBusy(true);
        startTransition(async () => {
          try {
            const result = await signInWithGoogleCredential(response.credential, next);
            if (result?.error) setGoogleError(result.error);
          } catch {
            setGoogleError('Could not complete Google sign-in. Please try again.');
          } finally {
            setBusy(false);
          }
        });
      },
    });
    window.google.accounts.id.renderButton(button, {
      theme: 'outline',
      size: 'large',
      text: 'continue_with',
      width: Math.min(Math.floor(button.getBoundingClientRect().width), 400),
    });
  };

  /*
   * Code length is a per-widget setting in MSG91 -- this one is set to 4
   * digits -- so the input is sized from what the widget reports rather than
   * a local guess.
   */
  const markWidgetReady = () => {
    setWidgetReady(true);
    const length = Number(window.getWidgetData?.()?.otpLength);
    if (Number.isFinite(length) && length >= 4 && length <= 8) setOtpLength(length);
  };

  const startWidget = () => {
    if (!configured) return;

    // Opened before: the widget is already initialised for this page load.
    if (window.sendOtp) {
      markWidgetReady();
      return;
    }
    if (!window.initSendOTP) return;

    window.initSendOTP({
      widgetId: WIDGET_ID,
      tokenAuth: TOKEN_AUTH,
      // No UI of MSG91's own -- it hands us sendOtp/verifyOtp/retryOtp on
      // `window` and we drive them from the storefront's own markup.
      exposeMethods: true,
      /*
       * Required. The provider throws "success callback function missing!"
       * without it, and because it defers that check into a setTimeout the
       * throw is asynchronous -- so the widget silently never mounts and
       * the exposed methods never appear. Verification results reach us
       * through the per-call callbacks below, so these two are only here to
       * satisfy the check.
       */
      success: () => undefined,
      failure: () => undefined,
    });

    /*
     * The methods are attached when the widget's component initialises, a
     * tick or two after this call, so readiness is polled rather than
     * assumed.
     */
    let waited = 0;
    const poll = window.setInterval(() => {
      waited += 100;
      if (window.sendOtp) {
        window.clearInterval(poll);
        markWidgetReady();
      } else if (waited >= 8000) {
        window.clearInterval(poll);
        setError('Could not start sign-in. Reload the page and try again.');
      }
    }, 100);
  };

  const sendCode = (event: React.FormEvent) => {
    event.preventDefault();
    const enteredValue = identifier.trim();
    if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(enteredValue)) {
      setError('Email verification is not available yet. Please use your mobile number.');
      return;
    }

    let digits = enteredValue.replace(/\D/g, '');
    if (digits.length === 12 && digits.startsWith(COUNTRY_CODE)) {
      digits = digits.slice(COUNTRY_CODE.length);
    }

    if (digits.length !== 10) {
      setError('Enter a valid email address or 10-digit mobile number.');
      return;
    }
    if (!widgetReady || !window.sendOtp) {
      setError('Sign-in is still loading. Try again in a moment.');
      return;
    }
    /*
     * MSG91's hCaptcha refuses localhost, and its encryption needs the Web
     * Crypto API that browsers only expose on HTTPS. Either way the widget
     * logs to the console and calls neither callback, so say so now rather
     * than sit on "Sending code…" until the watchdog fires.
     */
    if (!window.isSecureContext || ['localhost', '127.0.0.1'].includes(window.location.hostname)) {
      setError('Phone sign-in needs HTTPS on a real domain, so no code was sent. In development, use npm run dev:https.');
      return;
    }

    setError('');
    setPhone(digits);
    setBusy(true);

    /*
     * The widget runs an hCaptcha check before it sends anything, and when
     * that check errors it only logs to the console -- neither callback
     * fires. Without this the button would sit on "Sending code…" forever.
     */
    window.clearTimeout(sendWatchdogRef.current);
    sendWatchdogRef.current = window.setTimeout(() => {
      setBusy(false);
      setError('The security check did not complete, so no code was sent. Please try again.');
    }, SEND_TIMEOUT_MS);

    window.sendOtp(
      `${COUNTRY_CODE}${digits}`,
      () => {
        window.clearTimeout(sendWatchdogRef.current);
        setBusy(false);
        setError('');
        setStep('code');
        setSeconds(RESEND_SECONDS);
      },
      err => {
        window.clearTimeout(sendWatchdogRef.current);
        setBusy(false);
        setError(readError(err, 'Could not send the code. Check the number and try again.'));
      },
    );
  };

  const verify = (event: React.FormEvent) => {
    event.preventDefault();
    if (code.length !== otpLength || !window.verifyOtp) return;

    setError('');
    setBusy(true);
    window.verifyOtp(
      code,
      data => {
        const token = readToken(data);

        if (!token) {
          setBusy(false);
          setError('Verification did not return a token. Try again.');
          return;
        }

        /*
         * Inside a transition so Next applies the action's redirect. On
         * success the action redirects and never resolves with a value, so
         * only an actual `error` is worth showing -- treating "no result" as
         * a failure flashed a false error over a login that had worked.
         */
        startTransition(async () => {
          const result = await signInWithWidgetToken(token, next);
          setBusy(false);
          if (result?.error) {
            setError(result.error);
            setCode('');
          }
        });
      },
      err => {
        setBusy(false);
        setError(readError(err, 'That code was not right. Try again.'));
      },
    );
  };

  const resend = () => {
    if (!window.retryOtp) return;
    setError('');
    setCode('');
    setSeconds(RESEND_SECONDS);
    window.retryOtp(
      null,
      () => undefined,
      err => setError(readError(err, 'Could not resend the code.')),
    );
  };

  return (
    <>
      {configured && (
        <Script
          src="https://verify.msg91.com/otp-provider.js"
          strategy="afterInteractive"
          onReady={startWidget}
        />
      )}
      {googleConfigured && (
        <Script
          src="https://accounts.google.com/gsi/client"
          strategy="afterInteractive"
          onReady={initializeGoogle}
          onError={() => setGoogleError('Could not load Google sign-in. Check your connection and retry.')}
        />
      )}

      <div
        className={styles.overlay}
        onMouseDown={event => {
          if (event.target === event.currentTarget) onClose();
        }}>
        <div className={styles.modal} role="dialog" aria-modal="true" aria-labelledby="signin-modal-title">
          <button type="button" className={styles.close} onClick={onClose} aria-label="Close sign in">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M5 5l14 14M19 5L5 19" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </button>

          <div className={styles.brandPanel}>
            <div className={styles.brandLockup} role="img" aria-label="CliQ.">
              <span className={styles.brandSymbol} aria-hidden="true" />
              <span className={styles.brandWordmark} aria-hidden="true" />
            </div>
          </div>

          <section className={styles.formPanel}>
            <div className={styles.formInner}>
              <h2 id="signin-modal-title" className={styles.title}>Sign in</h2>

              {step === 'phone' ? (
                <form className={styles.fields} onSubmit={sendCode} noValidate>
                  <div className={styles.fieldGroup}>
                    <label className={styles.label} htmlFor="signin-identity">
                      Email or phone number
                    </label>
                    <input
                      ref={identityRef}
                      id="signin-identity"
                      type="text"
                      value={identifier}
                      onChange={event => setIdentifier(event.target.value)}
                      placeholder="Enter email or phone number"
                      autoComplete="username"
                      aria-invalid={error ? true : undefined}
                      aria-describedby={error ? 'signin-modal-error' : undefined}
                      className={styles.input}
                    />
                    {error && <p id="signin-modal-error" className={styles.error} role="alert">{error}</p>}
                  </div>

                  <button type="submit" className={styles.continue} disabled={busy || !configured}>
                    {busy ? 'Sending code…' : <>Continue <span aria-hidden="true">→</span></>}
                  </button>
                  {!configured && (
                    <p className={styles.error} role="status">
                      Mobile verification is unavailable. Continue with Google if enabled.
                    </p>
                  )}
                </form>
              ) : (
                <>
                  <p className={styles.verifyIntro}>
                    Enter the verification code sent to +{COUNTRY_CODE} {phone}.
                  </p>
                  <form className={styles.fields} onSubmit={verify} noValidate>
                    <div className={styles.fieldGroup}>
                      <label className={styles.label} htmlFor="signin-otp">OTP</label>
                      <input
                        ref={otpRef}
                        id="signin-otp"
                        type="text"
                        inputMode="numeric"
                        pattern="[0-9]*"
                        maxLength={otpLength}
                        value={code}
                        onChange={event => setCode(event.target.value.replace(/\D/g, '').slice(0, otpLength))}
                        placeholder="Enter verification code"
                        autoComplete="one-time-code"
                        aria-invalid={error ? true : undefined}
                        aria-describedby={error ? 'signin-modal-error' : undefined}
                        className={styles.input}
                      />
                      {error && <p id="signin-modal-error" className={styles.error} role="alert">{error}</p>}
                    </div>
                    <button type="submit" className={styles.continue} disabled={code.length !== otpLength || busy}>
                      {busy ? 'Verifying…' : <>Continue <span aria-hidden="true">→</span></>}
                    </button>
                  </form>
                  <div className={styles.resend}>
                    {seconds > 0 ? (
                      <span>Resend code in {seconds}s</span>
                    ) : (
                      <button type="button" onClick={resend}>Resend code</button>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        setStep('phone');
                        setCode('');
                        setError('');
                      }}>
                      Change number
                    </button>
                  </div>
                </>
              )}

              {googleConfigured && (
                <>
                  <div className={styles.divider}><span>OR CONTINUE WITH</span></div>
                  <div className={styles.googleButton}>
                    <div ref={googleButtonRef} />
                  </div>
                  {googleError && <p className={styles.error} role="alert">{googleError}</p>}
                </>
              )}

              <p className={styles.note}>
                New to CliQ? Your account is created after mobile verification.
              </p>
            </div>
          </section>
        </div>
      </div>
    </>
  );
}
