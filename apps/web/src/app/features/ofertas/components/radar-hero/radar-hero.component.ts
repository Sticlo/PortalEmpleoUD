import { Component, input, output } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-radar-hero',
  imports: [RouterLink],
  templateUrl: './radar-hero.component.html',
})
export class RadarHeroComponent {
  readonly scanning = input(false);
  readonly searchLive = input('');
  readonly subtitle = input('Computrabajo, Elempleo y LinkedIn · Bogotá');
  readonly btnLabel = input('Buscar');
  readonly query = input('desarrollador');
  readonly queryChange = output<string>();
  readonly search = output<string>();

  onQueryInput(event: Event): void {
    this.queryChange.emit((event.target as HTMLInputElement).value);
  }

  onSearchClick(event: Event): void {
    event.preventDefault();
    event.stopPropagation();
    const q = this.query().trim();
    if (!q || this.scanning()) return;
    this.search.emit(q);
  }

  onEnter(event: Event): void {
    event.preventDefault();
    this.onSearchClick(event);
  }
}
