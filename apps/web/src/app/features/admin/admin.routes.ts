import { Routes } from '@angular/router';

export const ADMIN_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () => import('./mercado.page').then((m) => m.MercadoPage),
  },
];
