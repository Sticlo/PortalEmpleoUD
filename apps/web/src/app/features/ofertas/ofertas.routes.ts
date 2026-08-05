import { Routes } from '@angular/router';

export const OFERTAS_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () => import('./ofertas.page').then((m) => m.OfertasPage),
    title: 'Ofertas · RutaUD',
  },
];
