import { Injectable, signal } from '@angular/core';
import { PRIVACY_POLICY_VERSION } from './privacy.config';

const CONSENT_KEY = 'rutaud.aiConsent';

/** Autorización expresa para enviar la HV a DeepSeek (transferencia internacional). */
@Injectable({ providedIn: 'root' })
export class AiConsentService {
  readonly granted = signal(this.load());

  accept(): void {
    try {
      localStorage?.setItem(CONSENT_KEY, PRIVACY_POLICY_VERSION);
    } catch {
      /* SSR / private */
    }
    this.granted.set(true);
  }

  revoke(): void {
    try {
      localStorage?.removeItem(CONSENT_KEY);
    } catch {
      /* SSR / private */
    }
    this.granted.set(false);
  }

  private load(): boolean {
    try {
      return localStorage?.getItem(CONSENT_KEY) === PRIVACY_POLICY_VERSION;
    } catch {
      return false;
    }
  }
}
