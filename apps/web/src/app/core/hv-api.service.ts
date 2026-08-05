import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { HvProfile } from './hv-profile.service';

/** Shape del StudentProfile de la API. */
export interface ApiStudentProfile {
  full_name: string;
  program_slug: string;
  semester?: number | null;
  email?: string | null;
  city: string;
  skills: string[];
  projects: string[];
  experience: string[];
  languages: string[];
  education: string[];
}

export interface ProfileUpsertResponse {
  student_id: string;
  profile: ApiStudentProfile;
}

export interface AdaptCvResponse {
  cv_text: string;
  notes: string;
}

const PROGRAM_SLUG: Record<string, string> = {
  'Ingeniería de Sistemas': 'ingenieria-de-sistemas',
  'Ingeniería Electrónica': 'ingenieria-electronica',
  'Ingeniería Industrial': 'ingenieria-industrial',
};

@Injectable({ providedIn: 'root' })
export class HvApiService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/v1';

  toApiProfile(p: HvProfile): ApiStudentProfile {
    const semesterMatch = p.semestre.match(/(\d+)/);
    const experience: string[] = [];
    if (p.cargo.trim() || p.empresa.trim()) {
      experience.push(
        [p.cargo, p.empresa ? `en ${p.empresa}` : '', p.periodo ? `(${p.periodo})` : '']
          .filter(Boolean)
          .join(' ')
          .trim(),
      );
    }
    p.logros
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean)
      .forEach((l) => experience.push(l));

    const email = p.contacto.includes('@') ? p.contacto.split(/[·,|]/)[0].trim() : p.contacto;

    return {
      full_name: p.nombre.trim(),
      program_slug: PROGRAM_SLUG[p.carrera] ?? 'ingenieria-de-sistemas',
      semester: semesterMatch ? Number(semesterMatch[1]) : null,
      email,
      city: p.ciudad || 'Bogotá',
      skills: [...p.skills],
      projects: [],
      experience,
      languages: [],
      education: [
        `${p.carrera} — ${p.semestre}`,
        p.universidad,
        `Busca: ${p.busca}`,
      ].filter(Boolean),
    };
  }

  saveProfile(studentId: string, profile: HvProfile): Observable<ProfileUpsertResponse> {
    return this.http.put<ProfileUpsertResponse>(
      `${this.base}/students/${encodeURIComponent(studentId)}/profile`,
      this.toApiProfile(profile),
    );
  }

  adaptCv(payload: {
    student_id: string;
    offer_title: string;
    offer_description: string;
    offer_company?: string;
  }): Observable<AdaptCvResponse> {
    return this.http.post<AdaptCvResponse>(`${this.base}/cv/adapt`, payload);
  }
}
