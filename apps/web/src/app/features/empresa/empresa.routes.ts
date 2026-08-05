import { Routes } from '@angular/router';

export const EMPRESA_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () => import('./empresa.page').then((m) => m.EmpresaPage),
    title: 'Publicar oferta · Empresas · RutaUD',
  },
];
