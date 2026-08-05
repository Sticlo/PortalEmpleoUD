import { Routes } from '@angular/router';
import { Shell } from './layout/shell';

export const routes: Routes = [
  {
    path: '',
    component: Shell,
    children: [
      {
        path: '',
        loadChildren: () => import('./features/home/home.routes').then((m) => m.HOME_ROUTES),
      },
      {
        path: 'hoja-de-vida',
        loadChildren: () => import('./features/hv/hv.routes').then((m) => m.HV_ROUTES),
      },
      {
        path: 'ofertas',
        loadChildren: () => import('./features/ofertas/ofertas.routes').then((m) => m.OFERTAS_ROUTES),
      },
      {
        path: 'cv/:offerId',
        loadChildren: () => import('./features/cv/cv.routes').then((m) => m.CV_ROUTES),
      },
      {
        path: 'empresa',
        loadChildren: () =>
          import('./features/empresa/empresa.routes').then((m) => m.EMPRESA_ROUTES),
      },
      {
        // Sección administrativa (piloto sin auth; luego rol/guard o se oculta del nav)
        path: 'admin/mercado',
        loadChildren: () => import('./features/admin/admin.routes').then((m) => m.ADMIN_ROUTES),
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
