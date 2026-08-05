import { isPlatformBrowser } from '@angular/common';
import {
  Component,
  Inject,
  OnInit,
  PLATFORM_ID,
  computed,
  inject,
  input,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { buildAdaptedAtsDocument, downloadAtsPdf } from '../../core/hv-ats-export';
import { OfferCard } from '../../core/models/offer';
import { HvApiService } from '../../core/hv-api.service';
import { HvProfileService } from '../../core/hv-profile.service';
import { buildCvFromProfile, careerMismatchNote } from '../../core/offer-mapper';
import { OffersStoreService } from '../../core/offers-store.service';
import { ToastService } from '../../core/toast.service';

@Component({
  selector: 'app-cv-page',
  imports: [RouterLink, FormsModule],
  templateUrl: './cv.page.html',
})
export class CvPage implements OnInit {
  readonly offerId = input.required<string>();
  readonly offer = signal<OfferCard | null>(null);
  readonly loading = signal(true);
  readonly adapting = signal(false);
  readonly cvText = signal('');
  readonly cvNotes = signal('');
  readonly affinity = signal(55);
  readonly matchedSkills = signal<string[]>([]);
  readonly missingSkills = signal<string[]>([]);
  readonly strengths = signal<string[]>([]);
  readonly editing = signal(false);
  /** Documento completo visible/editable (lo que se imprime en el PDF). */
  readonly draftDoc = signal('');

  readonly hv = inject(HvProfileService);
  private readonly store = inject(OffersStoreService);
  private readonly api = inject(HvApiService);
  private readonly router = inject(Router);
  private readonly toast = inject(ToastService);

  readonly fullDocument = computed(() => {
    if (this.editing() && this.draftDoc().trim()) {
      return this.draftDoc();
    }
    const card = this.offer();
    if (!card) return '';
    return buildAdaptedAtsDocument(this.hv.profile(), {
      offerTitle: card.title,
      company: card.company,
      body: this.cvText(),
    });
  });

  readonly eyeNote = computed(
    () => this.cvNotes() || this.offer()?.cvGap || 'Sin gaps críticos respecto a tu HV.',
  );

  readonly affinityLabel = computed(() => {
    const n = this.affinity();
    if (n >= 80) return 'Alta';
    if (n >= 60) return 'Buena';
    if (n >= 40) return 'Media';
    return 'Baja';
  });

  readonly affinityClass = computed(() => {
    const n = this.affinity();
    if (n >= 80) return 'cv-aff--high';
    if (n >= 60) return 'cv-aff--mid';
    return 'cv-aff--low';
  });

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
      this.applyLocal(card);
    }
  }

  private toApiOffer(card: OfferCard) {
    return {
      id: card.id,
      title: card.title,
      company: card.company,
      city: card.city,
      modality: card.modality,
      source: card.source,
      url: card.url,
      published_at: card.publishedAt,
      description: `${card.rawDescription} ${card.programLabel || ''}`.trim(),
      program_tags: card.programLabel ? [card.programLabel] : [],
    };
  }

  private applyLocal(card: OfferCard): void {
    const local = buildCvFromProfile(this.toApiOffer(card), this.hv.profile());
    const careerNote = careerMismatchNote(this.toApiOffer(card), this.hv.profile());
    this.cvText.set(local.body);
    this.cvNotes.set(local.gap);
    this.affinity.set(careerNote ? Math.min(card.match || 22, 22) : card.match || 55);
    this.matchedSkills.set([]);
    this.missingSkills.set([]);
    this.strengths.set(
      careerNote
        ? ['Puedes preparar el CV igual; el Ojo te advierte que el área no es la tuya.']
        : [],
    );
  }

  private async adapt(card: OfferCard): Promise<void> {
    this.adapting.set(true);
    try {
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
      let notes = res.notes || 'Sin gaps críticos respecto a tu HV.';
      const careerNote = careerMismatchNote(this.toApiOffer(card), this.hv.profile());
      if (
        careerNote &&
        !notes.toLowerCase().includes('carrera') &&
        !notes.toLowerCase().includes('apunta')
      ) {
        notes = `${careerNote} ${notes}`;
      }
      // Choque de carrera → el Ojo no puede quedar “bonito”
      let score = res.affinity_score ?? card.match ?? 55;
      if (careerNote) {
        score = Math.min(score, card.match, 22);
      }
      this.cvNotes.set(notes);
      this.affinity.set(score);
      this.matchedSkills.set(res.matched_skills ?? []);
      this.missingSkills.set(res.missing_skills ?? []);
      const strengths = [...(res.strengths ?? [])];
      if (careerNote && !strengths.some((s) => s.toLowerCase().includes('preparar el cv'))) {
        strengths.unshift(
          'Puedes preparar el CV igual; el Ojo te advierte que el área no es la tuya.',
        );
      }
      this.strengths.set(strengths);
      this.toast.show(`Afinidad ${score}% · HV lista`);
    } catch {
      this.applyLocal(card);
      this.toast.show('HV adaptada en modo local');
    } finally {
      this.adapting.set(false);
    }
  }

  toggleEdit(): void {
    if (!this.editing()) {
      // Entrar a editar con el documento completo (preview)
      const card = this.offer();
      const doc = card
        ? buildAdaptedAtsDocument(this.hv.profile(), {
            offerTitle: card.title,
            company: card.company,
            body: this.cvText(),
          })
        : this.cvText();
      this.draftDoc.set(doc);
      this.editing.set(true);
      return;
    }
    // Al salir, el draft se convierte en la fuente del PDF/preview
    if (this.draftDoc().trim()) {
      this.cvText.set(this.draftDoc().trim());
    }
    this.editing.set(false);
  }

  download(): void {
    if (!isPlatformBrowser(this.platformId)) return;
    const card = this.offer();
    if (!card) return;
    // Si está editando, guarda el draft primero
    const text = (this.editing() ? this.draftDoc() : this.fullDocument()).trim();
    if (!text) {
      this.toast.show('No hay contenido para descargar');
      return;
    }
    const nameSlug = (this.hv.profile().nombre || 'hv')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-zA-Z0-9]+/g, '-')
      .replace(/^-|-$/g, '')
      .toLowerCase()
      .slice(0, 24);
    const offerSlug = (card.title || 'oferta')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-zA-Z0-9]+/g, '-')
      .replace(/^-|-$/g, '')
      .toLowerCase()
      .slice(0, 28);
    downloadAtsPdf(text, `${nameSlug || 'hv'}-${offerSlug || 'oferta'}-ats.pdf`);
    this.toast.show('PDF descargado');
  }

  done(): void {
    void this.router.navigateByUrl('/ofertas');
  }
}
