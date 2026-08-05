import { Routes } from '@angular/router';

export const HV_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () => import('./hv.page').then((m) => m.HvPage),
    title: 'Mi hoja de vida · RutaUD',
  },
];
