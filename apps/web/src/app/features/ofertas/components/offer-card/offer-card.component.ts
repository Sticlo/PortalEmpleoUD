import { NgClass } from '@angular/common';
import { Component, input, output } from '@angular/core';
import { OfferCard } from '../../../../core/models/offer';

@Component({
  selector: 'app-offer-card',
  imports: [NgClass],
  templateUrl: './offer-card.component.html',
})
export class OfferCardComponent {
  readonly offer = input.required<OfferCard>();
  readonly index = input(0);
  readonly prepare = output<OfferCard>();
}
