import { isPlatformBrowser } from '@angular/common';
import {
  AfterViewInit,
  Component,
  DestroyRef,
  ElementRef,
  PLATFORM_ID,
  inject,
  viewChild,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { HvProfileService } from '../../core/hv-profile.service';
import { startLandingMotion } from './landing-motion';

interface Word {
  text: string;
  accent?: boolean;
}

const words = (sentence: string, accents: string[] = []): Word[] =>
  sentence.split(' ').map((text) => ({ text, accent: accents.includes(text) }));

@Component({
  selector: 'app-home-page',
  imports: [RouterLink],
  templateUrl: './home.page.html',
  styleUrl: './home.page.css',
})
export class HomePage implements AfterViewInit {
  readonly hv = inject(HvProfileService);
  private readonly root = viewChild.required<ElementRef<HTMLElement>>('landing');

  readonly repoUrl = 'https://github.com/Sticlo/PortalEmpleoUD';

  readonly sections = [
    { id: 'inicio', label: 'Inicio' },
    { id: 'como-funciona', label: 'Cómo funciona' },
    { id: 'proyecto', label: 'El proyecto' },
    { id: 'comunidad', label: 'Comunidad' },
  ];

  readonly heroWords = words('Tu primer empleo empieza aquí.', ['aquí.']);

  readonly manifesto = words(
    'RutaUD es un proyecto universitario independiente, hecho por un estudiante, con un solo fin: mejorar las condiciones laborales de quienes vienen detrás y acercarles oportunidades reales de práctica y primer empleo.',
    ['independiente,', 'estudiantes,', 'oportunidades', 'reales'],
  );

  readonly steps = [
    {
      n: '01',
      title: 'Arma tu hoja de vida',
      text: 'Paso a paso y en formato ATS. Ves tu CV formarse en vivo mientras escribes.',
      link: '/hoja-de-vida',
      cta: 'Empezar',
    },
    {
      n: '02',
      title: 'La IA busca por ti',
      text: 'Revisa varios portales de empleo y te deja solo ofertas frescas para tu carrera.',
      link: '/ofertas',
      cta: 'Ver ofertas',
    },
    {
      n: '03',
      title: 'Prepara y aplica',
      text: 'Un CV adaptado a cada oferta, con lo que de verdad sabes hacer. Sin vender humo.',
      link: '/ofertas',
      cta: 'Probar',
    },
    {
      n: '04',
      title: 'Comparte una oferta',
      text: '¿Sabes de una práctica o vacante? Publícala y llega a más estudiantes de la UD.',
      link: '/empresa',
      cta: 'Publicar',
    },
  ];

  private readonly platformId = inject(PLATFORM_ID);
  private readonly destroyRef = inject(DestroyRef);

  ngAfterViewInit(): void {
    if (!isPlatformBrowser(this.platformId)) return;
    const stop = startLandingMotion(this.root().nativeElement);
    this.destroyRef.onDestroy(stop);
  }

  go(id: string): void {
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    document.getElementById(id)?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' });
  }
}
