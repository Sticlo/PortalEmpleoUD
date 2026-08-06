import { isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { HvProfileService } from '../../core/hv-profile.service';
import { OfferCard } from '../../core/models/offer';
import { searchQueryFromProfile } from '../../core/offer-mapper';
import { OffersStoreService } from '../../core/offers-store.service';
import { ToastService } from '../../core/toast.service';
import { OfferCardComponent } from './components/offer-card/offer-card.component';
import { RadarHeroComponent } from './components/radar-hero/radar-hero.component';

@Component({
  selector: 'app-ofertas-page',
  imports: [RadarHeroComponent, OfferCardComponent],
  templateUrl: './ofertas.page.html',
})
export class OfertasPage implements OnInit {
  readonly store = inject(OffersStoreService);
  readonly scanning = signal(false);
  readonly showResults = signal(false);
  readonly searchLive = signal('');
  readonly subtitle = signal('Computrabajo, Elempleo y LinkedIn · Bogotá');
  readonly btnLabel = signal('Buscar');
  readonly searchQuery = signal('desarrollador');

  private readonly router = inject(Router);
  private readonly toast = inject(ToastService);
  private readonly hv = inject(HvProfileService);

  constructor(@Inject(PLATFORM_ID) private readonly platformId: object) {}

  ngOnInit(): void {
    this.searchQuery.set(searchQueryFromProfile(this.hv.profile()));
    if (isPlatformBrowser(this.platformId)) {
      void this.store.loadToday();
      if (this.store.cards().length) {
        this.showResults.set(true);
        this.btnLabel.set('Buscar de nuevo');
        this.subtitle.set('Resultados listos. Cambia la palabra para refrescar.');
      }
    }
  }

  async runSearch(queryFromInput?: string): Promise<void> {
    if (!isPlatformBrowser(this.platformId)) return;

    const q = (queryFromInput ?? this.searchQuery()).trim();
    if (!q) {
      this.toast.show('Escribe una palabra clave');
      return;
    }
    this.searchQuery.set(q);

    this.showResults.set(false);
    this.scanning.set(true);
    this.btnLabel.set('Buscar');
    this.searchLive.set(`«${q}» · Computrabajo, Elempleo y LinkedIn`);

    try {
      const cards = await this.store.search(q);
      const purged = this.store.lastPurged();

      this.searchLive.set('');
      this.subtitle.set(
        cards.length
          ? `«${q}» · ≤24 h · elige una y prepara tu CV`
          : `Sin resultados para «${q}». Prueba otra palabra.`,
      );
      if (purged > 0) {
        this.subtitle.update((s) => `${s} · ${purged} vencidas eliminadas`);
      }
      this.btnLabel.set('Buscar de nuevo');
      this.showResults.set(true);
      const note = this.store.searchNote();
      this.toast.show(
        cards.length
          ? note.includes('ocupados')
            ? `${cards.length} del índice (portales ocupados)`
            : `${cards.length} ofertas encontradas`
          : note || 'Sin ofertas nuevas',
      );
    } catch (err) {
      console.error('Error scrape ofertas', err);
      this.searchLive.set('');
      this.subtitle.set('No se pudo conectar con la API. ¿Está activa en :8000?');
      this.btnLabel.set('Reintentar');
      this.showResults.set(false);
      this.toast.show('Error de conexión con la API');
    } finally {
      this.scanning.set(false);
    }
  }

  prepareCv(offer: OfferCard): void {
    void this.router.navigate(['/cv', offer.id]);
  }
}
