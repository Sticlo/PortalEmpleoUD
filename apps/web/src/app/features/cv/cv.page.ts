import { isPlatformBrowser } from '@angular/common';
import {
  Component,
  Inject,
  OnInit,
  PLATFORM_ID,
  inject,
  input,
  signal,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { OfferCard } from '../../core/models/offer';
import { HvApiService } from '../../core/hv-api.service';
import { HvProfileService } from '../../core/hv-profile.service';
import { buildCvFromProfile } from '../../core/offer-mapper';
import { OffersStoreService } from '../../core/offers-store.service';
import { ToastService } from '../../core/toast.service';
import { CvResultComponent } from './components/cv-result/cv-result.component';

@Component({
  selector: 'app-cv-page',
  imports: [RouterLink, CvResultComponent],
  templateUrl: './cv.page.html',
})
export class CvPage implements OnInit {
  readonly offerId = input.required<string>();
  readonly offer = signal<OfferCard | null>(null);
  readonly loading = signal(true);
  readonly adapting = signal(false);
  readonly cvText = signal('');
  readonly cvNotes = signal('');
  readonly adaptedWithAi = signal(false);

  readonly hv = inject(HvProfileService);
  private readonly store = inject(OffersStoreService);
  private readonly api = inject(HvApiService);
  private readonly router = inject(Router);
  private readonly toast = inject(ToastService);

  constructor(@Inject(PLATFORM_ID) private readonly platformId: object) {}

  ngOnInit(): void {
    void this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    let card = this.store.getById(this.offerId()) ?? null;
    if (!card && isPlatformBrowser(this.platformId)) {
      card = await this.store.ensureOffer(this.offerId());
    }
    this.offer.set(card);
    this.loading.set(false);

    if (card && isPlatformBrowser(this.platformId)) {
      await this.adapt(card);
    } else if (card) {
      const local = buildCvFromProfile(
        {
          id: card.id,
          title: card.title,
          company: card.company,
          city: card.city,
          modality: card.modality,
          source: card.source,
          url: card.url,
          published_at: card.publishedAt,
          description: card.rawDescription,
          program_tags: [],
        },
        this.hv.profile(),
      );
      this.cvText.set(local.body);
      this.cvNotes.set(local.gap);
    }
  }

  private async adapt(card: OfferCard): Promise<void> {
    this.adapting.set(true);
    try {
      // Asegura perfil en API antes de adaptar
      await firstValueFrom(this.api.saveProfile(this.hv.studentId(), this.hv.profile()));
      const res = await firstValueFrom(
        this.api.adaptCv({
          student_id: this.hv.studentId(),
          offer_title: card.title,
          offer_description: card.rawDescription || card.description,
          offer_company: card.company,
        }),
      );
      this.cvText.set(res.cv_text);
      this.cvNotes.set(res.notes || 'Sin gaps críticos respecto a tu HV.');
      this.adaptedWithAi.set(true);
    } catch {
      const local = buildCvFromProfile(
        {
          id: card.id,
          title: card.title,
          company: card.company,
          city: card.city,
          modality: card.modality,
          source: card.source,
          url: card.url,
          published_at: card.publishedAt,
          description: card.rawDescription,
          program_tags: [],
        },
        this.hv.profile(),
      );
      this.cvText.set(local.body);
      this.cvNotes.set(local.gap);
      this.adaptedWithAi.set(false);
      this.toast.show('CV local (API de adaptación no disponible)');
    } finally {
      this.adapting.set(false);
    }
  }

  async copy(): Promise<void> {
    if (!isPlatformBrowser(this.platformId)) return;
    const text = [
      this.hv.profile().nombre,
      `${this.hv.profile().carrera} · ${this.hv.profile().semestre} · Universidad Distrital`,
      this.cvText(),
      `Ojo: ${this.cvNotes()}`,
    ].join('\n\n');
    try {
      await navigator.clipboard.writeText(text);
      this.toast.show('CV copiado');
    } catch {
      this.toast.show('Selecciona y copia el texto');
    }
  }

  done(): void {
    void this.router.navigateByUrl('/ofertas');
  }
}
