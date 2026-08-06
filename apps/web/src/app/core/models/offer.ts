/** Oferta tal como la expone la API. */
export interface ApiOffer {
  id: string;
  title: string;
  company: string;
  city: string;
  modality: string;
  source: string;
  url?: string | null;
  published_at: string;
  description: string;
  salary?: string | null;
  program_tags: string[];
}

/** Vista de tarjeta en el radar. */
export interface OfferCard {
  id: string;
  source: string;
  sourceClass: string;
  fresh: string;
  title: string;
  company: string;
  companyLine: string;
  city: string;
  modality: string;
  modalityLabel: string;
  salary: string;
  description: string;
  programLabel: string;
  match: number;
  matchClass: 'match--high' | 'match--mid' | 'match--low';
  recommended: boolean;
  url?: string | null;
  publishedAt: string;
  rawDescription: string;
  cvTitle: string;
  cvBody: string;
  cvGap: string;
}

export interface IndexedSearchResponse {
  query: string;
  city: string;
  count: number;
  offers: ApiOffer[];
  source: string;
  note: string;
}

export interface ScrapeResponse {
  query: string;
  city: string;
  max_age_hours: number;
  scrapers: string[];
  imported: number;
  purged: number;
  per_source: Record<string, number>;
  errors: { source: string; error: string }[];
  offers: ApiOffer[];
  from_cache?: boolean;
  shared_waiters?: number;
  queue_note?: string;
}

export interface OfferListResponse {
  filters: {
    city: string;
    max_age_hours: number;
    program_slug: string;
    prefer_modality: string;
  };
  count: number;
  offers: ApiOffer[];
  purged: number;
}

export interface TodayJobsResponse {
  day: string;
  title: string;
  count: number;
  offers: ApiOffer[];
  programs_covered: string[];
  note?: string;
}
