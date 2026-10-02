import { Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { AiConsentService } from '../../core/ai-consent.service';
import { HvApiService } from '../../core/hv-api.service';
import { HvProfileService } from '../../core/hv-profile.service';
import {
  PRIVACY_CONTACT_EMAIL,
  PRIVACY_POLICY_VERSION,
  PRIVACY_RESPONSIBLE,
} from '../../core/privacy.config';
import { ToastService } from '../../core/toast.service';

@Component({
  selector: 'app-privacidad-page',
  imports: [RouterLink],
  templateUrl: './privacidad.page.html',
})
export class PrivacidadPage {
  readonly responsible = PRIVACY_RESPONSIBLE;
  readonly contactEmail = PRIVACY_CONTACT_EMAIL;
  readonly version = PRIVACY_POLICY_VERSION;
  readonly deleting = signal(false);

  readonly consent = inject(AiConsentService);
  private readonly hv = inject(HvProfileService);
  private readonly api = inject(HvApiService);
  private readonly toast = inject(ToastService);

  revokeAi(): void {
    this.consent.revoke();
    this.toast.show('Autorización de IA revocada');
  }

  async deleteMyData(): Promise<void> {
    this.deleting.set(true);
    try {
      await firstValueFrom(this.api.deleteProfile(this.hv.studentId()));
    } catch {
      /* el perfil puede no existir en el servidor (se borra al reiniciar) */
    }
    this.hv.clearLocalData();
    this.consent.revoke();
    this.deleting.set(false);
    this.toast.show('Tus datos fueron borrados de este navegador y del servidor');
  }
}
