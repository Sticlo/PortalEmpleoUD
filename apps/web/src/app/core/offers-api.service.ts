import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import {
  ApiOffer,
  IndexedSearchResponse,
  OfferListResponse,
  ScrapeResponse,
  TodayJobsResponse,
} from './models/offer';

@Injectable({ providedIn: 'root' })
export class OffersApiService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/v1';

  /** Rápido: histórico + memoria. No toca portales. */
  searchIndexed(query: string, city = 'Bogotá'): Observable<IndexedSearchResponse> {
    return this.http.get<IndexedSearchResponse>(`${this.base}/offers/search`, {
      params: { q: query, city, days: 30, limit: 40 },
    });
  }

  /** En vivo: cola + caché anti-stampede. */
  scrape(query: string, city = 'Bogotá', maxAgeHours = 24): Observable<ScrapeResponse> {
    return this.http.post<ScrapeResponse>(`${this.base}/scraping/run`, {
      query,
      city,
      max_age_hours: maxAgeHours,
    });
  }

  list(city = 'Bogotá', maxAgeHours = 24): Observable<OfferListResponse> {
    return this.http.get<OfferListResponse>(`${this.base}/offers`, {
      params: { city, max_age_hours: maxAgeHours },
    });
  }

  today(): Observable<TodayJobsResponse> {
    return this.http.get<TodayJobsResponse>(`${this.base}/offers/today`);
  }

  getById(id: string): Observable<ApiOffer> {
    return this.http.get<ApiOffer>(`${this.base}/offers/${encodeURIComponent(id)}`);
  }
}
