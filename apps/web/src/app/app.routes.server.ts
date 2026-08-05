import { RenderMode, ServerRoute } from '@angular/ssr';

export const serverRoutes: ServerRoute[] = [
  { path: '', renderMode: RenderMode.Prerender },
  { path: 'hoja-de-vida', renderMode: RenderMode.Prerender },
  // Interactiva (HTTP al scraper): debe correr en el browser, no SSG
  { path: 'ofertas', renderMode: RenderMode.Client },
  { path: 'cv/:offerId', renderMode: RenderMode.Client },
  { path: 'empresa', renderMode: RenderMode.Client },
  { path: '**', renderMode: RenderMode.Server },
];
