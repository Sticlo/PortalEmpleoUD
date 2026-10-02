import { Routes } from '@angular/router';

export const HOME_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () => import('./home.page').then((m) => m.HomePage),
    title: 'RutaUD · Prácticas y primer empleo para estudiantes UD',
  },
];
