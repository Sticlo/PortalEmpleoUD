import { Component, input, output } from '@angular/core';
import { RouterLink } from '@angular/router';
import { OfferCard } from '../../../../core/models/offer';
import { HvProfile } from '../../../../core/hv-profile.service';

@Component({
  selector: 'app-cv-result',
  imports: [RouterLink],
  templateUrl: './cv-result.component.html',
})
export class CvResultComponent {
  readonly offer = input.required<OfferCard>();
  readonly profile = input.required<HvProfile>();
  readonly cvText = input('');
  readonly cvNotes = input('');
  readonly adaptedWithAi = input(false);
  readonly copy = output<void>();
  readonly done = output<void>();
}
