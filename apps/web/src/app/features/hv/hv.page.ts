import { isPlatformBrowser } from '@angular/common';
import { Component, Inject, PLATFORM_ID, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { downloadAtsPdfFromProfile } from '../../core/hv-ats-export';
import { HvApiService } from '../../core/hv-api.service';
import { HvProfileService } from '../../core/hv-profile.service';
import { ToastService } from '../../core/toast.service';
import { AtsFormComponent } from './components/ats-form/ats-form.component';
import { AtsPreviewComponent } from './components/ats-preview/ats-preview.component';
import { AtsStepsComponent } from './components/ats-steps/ats-steps.component';

@Component({
  selector: 'app-hv-page',
  imports: [AtsStepsComponent, AtsFormComponent, AtsPreviewComponent],
  templateUrl: './hv.page.html',
})
export class HvPage {
  readonly step = signal(0);
  readonly totalSteps = 5;
  readonly saving = signal(false);
  readonly stepError = signal('');

  readonly hv = inject(HvProfileService);
  private readonly api = inject(HvApiService);
  private readonly router = inject(Router);
  private readonly toast = inject(ToastService);

  constructor(@Inject(PLATFORM_ID) private readonly platformId: object) {
    if (isPlatformBrowser(this.platformId)) {
      // Sanea skills pegadas con "·" de versiones anteriores
      this.hv.setSkills(this.hv.profile().skills);
    }
  }

  setStep(n: number): void {
    this.stepError.set('');
    this.step.set(Math.max(0, Math.min(this.totalSteps - 1, n)));
  }

  next(): void {
    const errors = this.hv.stepErrors(this.step());
    if (errors.length) {
      this.stepError.set(errors[0]);
      this.toast.show(errors[0]);
      return;
    }
    this.stepError.set('');
    this.setStep(this.step() + 1);
  }

  prev(): void {
    this.stepError.set('');
    this.setStep(this.step() - 1);
  }

  downloadAts(): void {
    if (!isPlatformBrowser(this.platformId)) return;
    if (!this.hv.profile().nombre.trim()) {
      this.setStep(0);
      this.toast.show('Escribe tu nombre antes de descargar');
      return;
    }
    downloadAtsPdfFromProfile(this.hv.profile());
    this.toast.show('PDF de tu HV descargado');
  }

  async save(): Promise<void> {
    const skillErrors = this.hv.stepErrors(4);
    if (skillErrors.length) {
      this.stepError.set(skillErrors[0]);
      this.toast.show(skillErrors[0]);
      this.setStep(4);
      return;
    }
    if (!this.hv.profile().nombre.trim()) {
      this.setStep(0);
      this.toast.show('Escribe tu nombre antes de guardar');
      return;
    }

    this.saving.set(true);
    try {
      if (isPlatformBrowser(this.platformId)) {
        await firstValueFrom(this.api.saveProfile(this.hv.studentId(), this.hv.profile()));
      }
      this.hv.markSaved();
      this.toast.show('HV ATS guardada · lista para adaptar a cada oferta');
      void this.router.navigateByUrl('/ofertas');
    } catch {
      this.hv.markSaved();
      this.toast.show('HV guardada en este dispositivo (API no disponible)');
      void this.router.navigateByUrl('/ofertas');
    } finally {
      this.saving.set(false);
    }
  }
}
