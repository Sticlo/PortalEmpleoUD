import { Routes } from '@angular/router';

export const PRIVACIDAD_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () => import('./privacidad.page').then((m) => m.PrivacidadPage),
    title: 'Aviso de privacidad · RutaUD',
  },
];
