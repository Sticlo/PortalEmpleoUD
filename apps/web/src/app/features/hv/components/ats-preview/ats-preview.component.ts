import { Component, inject } from '@angular/core';
import { HvProfileService } from '../../../../core/hv-profile.service';

@Component({
  selector: 'app-ats-preview',
  templateUrl: './ats-preview.component.html',
})
export class AtsPreviewComponent {
  readonly hv = inject(HvProfileService);
}
