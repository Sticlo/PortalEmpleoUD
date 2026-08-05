import { isPlatformBrowser } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, Inject, PLATFORM_ID, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { ToastService } from '../../core/toast.service';

interface PublishPayload {
  title: string;
  company: string;
  description: string;
  salary: string;
  city: string;
  modality: string;
  contact_email: string;
  apply_url: string;
  program_slug: string;
}

@Component({
  selector: 'app-empresa-page',
  imports: [FormsModule, RouterLink],
  templateUrl: './empresa.page.html',
})
export class EmpresaPage {
  readonly submitting = signal(false);
  readonly publishedId = signal<string | null>(null);
  readonly error = signal('');

  form: PublishPayload = {
    title: '',
    company: '',
    description: '',
    salary: '',
    city: 'Bogotá',
    modality: 'hibrido',
    contact_email: '',
    apply_url: '',
    program_slug: 'ingenieria-de-sistemas',
  };

  private readonly http = inject(HttpClient);
  private readonly toast = inject(ToastService);
  private readonly router = inject(Router);

  constructor(@Inject(PLATFORM_ID) private readonly platformId: object) {}

  async submit(event: Event): Promise<void> {
    event.preventDefault();
    this.error.set('');

    if (this.form.title.trim().length < 3) {
      this.error.set('Indica un título claro de la vacante');
      return;
    }
    if (this.form.company.trim().length < 2) {
      this.error.set('Indica el nombre de la empresa');
      return;
    }
    if (this.form.description.trim().length < 20) {
      this.error.set('La descripción debe tener al menos 20 caracteres');
      return;
    }

    if (!isPlatformBrowser(this.platformId)) return;

    this.submitting.set(true);
    try {
      const body = {
        title: this.form.title.trim(),
        company: this.form.company.trim(),
        description: this.form.description.trim(),
        salary: this.form.salary.trim() || null,
        city: this.form.city.trim() || 'Bogotá',
        modality: this.form.modality,
        contact_email: this.form.contact_email.trim() || null,
        apply_url: this.form.apply_url.trim() || null,
        program_slug: this.form.program_slug,
      };
      const res = await firstValueFrom(
        this.http.post<{ ok: boolean; id: string; message?: string }>(
          '/api/v1/offers/publish',
          body,
        ),
      );
      this.publishedId.set(res.id);
      this.toast.show('Oferta publicada');
    } catch (err) {
      console.error(err);
      this.error.set('No se pudo publicar. ¿La API está en :8000?');
      this.toast.show('Error al publicar');
    } finally {
      this.submitting.set(false);
    }
  }

  goOffers(): void {
    void this.router.navigateByUrl('/ofertas');
  }

  reset(): void {
    this.publishedId.set(null);
    this.form = {
      title: '',
      company: '',
      description: '',
      salary: '',
      city: 'Bogotá',
      modality: 'hibrido',
      contact_email: '',
      apply_url: '',
      program_slug: 'ingenieria-de-sistemas',
    };
  }
}
