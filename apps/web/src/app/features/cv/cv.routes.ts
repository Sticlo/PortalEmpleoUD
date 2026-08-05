import { Routes } from '@angular/router';

export const CV_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () => import('./cv.page').then((m) => m.CvPage),
    title: 'Preparar CV · RutaUD',
  },
];
