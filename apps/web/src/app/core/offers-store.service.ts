import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { HvProfileService } from './hv-profile.service';
import { searchQueryFromProfile, toOfferCard } from './offer-mapper';
import { ApiOffer, OfferCard } from './models/offer';
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
  readonly lastWindowHours = signal(24);
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
  async search(query?: string, force = false): Promise<OfferCard[]> {
    this.loading.set(true);
    this.refreshingLive.set(true);
    this.error.set(null);
    this.searchNote.set('');
    this.cards.set([]); // limpia resultados viejos → el usuario ve spinner, no ofertas ajenas
    const profile = this.hv.profile();
    const q = (query ?? searchQueryFromProfile(profile)).trim() || 'desarrollador';
    const city = profile.ciudad || 'Bogotá';
    this.lastQuery.set(q);

    const applyResult = (res: {
      offers?: ApiOffer[];
      purged?: number;
      from_cache?: boolean;
      queue_note?: string;
      freshness_note?: string;
      max_age_hours?: number;
      errors?: { source: string; error: string }[];
    }): OfferCard[] => {
      this.lastPurged.set(res.purged ?? 0);
      this.lastWindowHours.set(res.max_age_hours ?? 24);
      if (res.errors?.length) {
        console.warn('Errores de scrapers', res.errors);
      }
      const cards = (res.offers ?? []).map((o) => toOfferCard(o, profile));
      cards.sort((a, b) => b.match - a.match);
      this.cards.set(cards);
      const bits = [res.freshness_note, res.queue_note].filter(
        (n): n is string => Boolean(n && n.trim()),
      );
      this.searchNote.set(
        bits.join(' ') ||
          (res.from_cache
            ? 'Misma búsqueda reciente: resultado compartido (sin re-golpear portales).'
            : 'Resultados de portales'),
      );
      return cards;
    };

    try {
      const res = await firstValueFrom(this.api.scrape(q, city, 24, force));
      const cards = applyResult(res);
      if (cards.length) return cards;

      // 200 vacío: índice estricto (no dejar la demo en cero si hay histórico)
      try {
        const indexed = await firstValueFrom(this.api.searchIndexed(q, city));
        const fromIndex = applyResult({
          offers: indexed.offers,
          purged: 0,
          from_cache: false,
          queue_note: indexed.note,
          freshness_note: '',
        });
        if (fromIndex.length) {
          this.searchNote.set(
            'Portales sin vacantes frescas · coincidencias del índice (filtro estricto)',
          );
        }
        return fromIndex;
      } catch {
        return [];
      }
    } catch (err) {
      // Cola llena / timeout → índice estricto (solo si coincide de verdad)
      try {
        const indexed = await firstValueFrom(this.api.searchIndexed(q, city));
        const cards = applyResult({
          offers: indexed.offers,
          purged: 0,
          from_cache: false,
          queue_note: indexed.note,
        });
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
