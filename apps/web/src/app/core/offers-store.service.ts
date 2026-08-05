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
  readonly lastQuery = signal('');
  readonly lastPurged = signal(0);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  readonly count = computed(() => this.cards().length);

  getById(id: string): OfferCard | undefined {
    return this.cards().find((o) => o.id === id);
  }

  async search(query?: string): Promise<OfferCard[]> {
    this.loading.set(true);
    this.error.set(null);
    const profile = this.hv.profile();
    const q = (query ?? searchQueryFromProfile(profile)).trim() || 'desarrollador';
    this.lastQuery.set(q);

    try {
      const res = await firstValueFrom(this.api.scrape(q, profile.ciudad || 'Bogotá', 24));
      this.lastPurged.set(res.purged ?? 0);
      if (res.errors?.length) {
        console.warn('Errores de scrapers', res.errors);
      }
      const cards = (res.offers ?? []).map((o) => toOfferCard(o, profile));
      cards.sort((a, b) => b.match - a.match);
      this.cards.set(cards);
      return cards;
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : 'No se pudo conectar con la API de ofertas';
      this.error.set(msg);
      this.cards.set([]);
      throw err;
    } finally {
      this.loading.set(false);
    }
  }

  async ensureOffer(id: string): Promise<OfferCard | null> {
    const cached = this.getById(id);
    if (cached) return cached;

    try {
      const offer = await firstValueFrom(this.api.getById(id));
      const card = toOfferCard(offer, this.hv.profile());
      this.cards.update((list) => (list.some((o) => o.id === id) ? list : [...list, card]));
      return card;
    } catch {
      return null;
    }
  }
}
