import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { HvProfileService } from './hv-profile.service';
import { searchQueryFromProfile, toOfferCard } from './offer-mapper';
import { OfferCard } from './models/offer';
import { OffersApiService } from './offers-api.service';

@Injectable({ providedIn: 'root' })
export class OffersStoreService {
  private readonly api = inject(OffersApiService);
  private readonly hv = inject(HvProfileService);

  readonly cards = signal<OfferCard[]>([]);
  readonly todayCards = signal<OfferCard[]>([]);
  readonly todayDay = signal('');
  readonly todayPrograms = signal<string[]>([]);
  readonly lastQuery = signal('');
  readonly lastPurged = signal(0);
  readonly loading = signal(false);
  readonly loadingToday = signal(false);
  readonly refreshingLive = signal(false);
  readonly searchNote = signal('');
  readonly error = signal<string | null>(null);

  readonly count = computed(() => this.cards().length);
  readonly todayCount = computed(() => this.todayCards().length);

  getById(id: string): OfferCard | undefined {
    return this.cards().find((o) => o.id === id) ?? this.todayCards().find((o) => o.id === id);
  }

  async loadToday(): Promise<OfferCard[]> {
    this.loadingToday.set(true);
    try {
      const res = await firstValueFrom(this.api.today());
      const profile = this.hv.profile();
      const cards = (res.offers ?? []).map((o) => {
        const card = toOfferCard(o, profile);
        return { ...card, recommended: true };
      });
      this.todayCards.set(cards);
      this.todayDay.set(res.day || '');
      this.todayPrograms.set(res.programs_covered || []);
      return cards;
    } catch (err) {
      console.warn('No se pudieron cargar Empleos de hoy', err);
      this.todayCards.set([]);
      return [];
    } finally {
      this.loadingToday.set(false);
    }
  }

  /**
   * Spinner hasta tener resultados de la búsqueda pedida.
   * - Preferimos scrape en vivo (cola anti-ban + caché de la MISMA query).
   * - Índice local solo como fallback si portales/cola fallan (filtro estricto).
   * No pintamos “basura” de otra búsqueda mientras carga.
   */
  async search(query?: string): Promise<OfferCard[]> {
    this.loading.set(true);
    this.refreshingLive.set(true);
    this.error.set(null);
    this.searchNote.set('');
    this.cards.set([]); // limpia resultados viejos → el usuario ve spinner, no ofertas ajenas
    const profile = this.hv.profile();
    const q = (query ?? searchQueryFromProfile(profile)).trim() || 'desarrollador';
    const city = profile.ciudad || 'Bogotá';
    this.lastQuery.set(q);

    try {
      const res = await firstValueFrom(this.api.scrape(q, city, 24));
      this.lastPurged.set(res.purged ?? 0);
      if (res.errors?.length) {
        console.warn('Errores de scrapers', res.errors);
      }
      const cards = (res.offers ?? []).map((o) => toOfferCard(o, profile));
      cards.sort((a, b) => b.match - a.match);
      this.cards.set(cards);
      this.searchNote.set(
        res.from_cache
          ? res.queue_note ||
              'Misma búsqueda reciente: resultado compartido (sin re-golpear portales).'
          : res.queue_note || 'Resultados de portales',
      );
      return cards;
    } catch (err) {
      // Cola llena / timeout → índice estricto (solo si coincide de verdad)
      try {
        const indexed = await firstValueFrom(this.api.searchIndexed(q, city));
        const cards = (indexed.offers ?? []).map((o) => toOfferCard(o, profile));
        cards.sort((a, b) => b.match - a.match);
        this.cards.set(cards);
        this.searchNote.set(
          cards.length
            ? 'Portales ocupados · mostrando coincidencias del índice (filtro estricto)'
            : 'Portales ocupados y sin coincidencias en índice · reintenta en un minuto',
        );
        this.error.set(null);
        return cards;
      } catch {
        const msg =
          err instanceof Error ? err.message : 'No se pudo conectar con la API de ofertas';
        this.error.set(msg);
        this.cards.set([]);
        throw err;
      }
    } finally {
      this.loading.set(false);
      this.refreshingLive.set(false);
    }
  }

  async ensureOffer(id: string): Promise<OfferCard | null> {
    const cached = this.getById(id);
    if (cached) return cached;

    try {
      const offer = await firstValueFrom(this.api.getById(id));
      const card = toOfferCard(offer, this.hv.profile());
      if (offer.source === 'empleos-de-hoy') {
        this.todayCards.update((list) =>
          list.some((o) => o.id === id) ? list : [...list, card],
        );
      } else {
        this.cards.update((list) => (list.some((o) => o.id === id) ? list : [...list, card]));
      }
      return card;
    } catch {
      return null;
    }
  }
}
