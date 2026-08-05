import { Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { HvProfileService } from '../../../../core/hv-profile.service';

@Component({
  selector: 'app-home-hero',
  imports: [RouterLink],
  templateUrl: './home-hero.component.html',
})
export class HomeHeroComponent {
  readonly hv = inject(HvProfileService);
}
