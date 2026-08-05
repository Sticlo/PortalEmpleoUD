import { Component, inject, output } from '@angular/core';
import { HvProfileService } from '../../../../core/hv-profile.service';

@Component({
  selector: 'app-ats-preview',
  templateUrl: './ats-preview.component.html',
})
export class AtsPreviewComponent {
  readonly hv = inject(HvProfileService);
  /** Click en sección → saltar al paso del wizard */
  readonly jumpToStep = output<number>();

  bullets(logros: string): string[] {
    return logros
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean);
  }

  hasExperience(): boolean {
    return this.hv
      .profile()
      .experiences.some((e) => e.cargo.trim() || e.empresa.trim() || e.logros.trim());
  }
}
