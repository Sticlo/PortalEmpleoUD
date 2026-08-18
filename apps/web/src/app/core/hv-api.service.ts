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
  affinity_score?: number;
  matched_skills?: string[];
  missing_skills?: string[];
  strengths?: string[];
  provider?: 'deepseek' | 'local' | string;
  model?: string | null;
}

const PROGRAM_SLUG: Record<string, string> = {
  'Ingeniería de Sistemas': 'ingenieria-de-sistemas',
  'Ingeniería Catastral y Geodesia': 'ingenieria-catastral',
  'Ingeniería Civil': 'ingenieria-civil',
  'Ingeniería Electrónica': 'ingenieria-electronica',
  'Ingeniería Forestal': 'ingenieria-forestal',
  'Ingeniería Química': 'ingenieria-quimica',
  'Ingeniería Industrial': 'ingenieria-industrial',
  'Licenciatura en Artes': 'licenciatura-en-artes',
};

function programSlugFromCarrera(carrera: string): string {
  const exact = PROGRAM_SLUG[carrera.trim()];
  if (exact) return exact;
  const c = carrera.toLowerCase();
  if (/catastr|geodes/.test(c)) return 'ingenieria-catastral';
  if (/civil/.test(c)) return 'ingenieria-civil';
  if (/electr/.test(c)) return 'ingenieria-electronica';
  if (/forestal|ambiental/.test(c)) return 'ingenieria-forestal';
  if (/qu[ií]mic/.test(c)) return 'ingenieria-quimica';
  if (/industrial/.test(c)) return 'ingenieria-industrial';
  if (/artes/.test(c)) return 'licenciatura-en-artes';
  if (/sistema|software|datos|telem[aá]tica|inform[aá]tica|computaci/.test(c)) {
    return 'ingenieria-de-sistemas';
  }
  // Carrera libre: slug legible para la API
  return (
    c
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '')
      .slice(0, 64) || 'otra-carrera-ud'
  );
}

@Injectable({ providedIn: 'root' })
export class HvApiService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/v1';

  toApiProfile(p: HvProfile): ApiStudentProfile {
    const semesterMatch = p.semestre.match(/(\d+)/);
    const experience: string[] = [];
    for (const exp of p.experiences) {
      if (exp.cargo.trim() || exp.empresa.trim()) {
        experience.push(
          [exp.cargo, exp.empresa ? `en ${exp.empresa}` : '', exp.periodo ? `(${exp.periodo})` : '']
            .filter(Boolean)
            .join(' ')
            .trim(),
        );
      }
      exp.logros
        .split('\n')
        .map((l) => l.trim())
        .filter(Boolean)
        .forEach((l) => experience.push(l));
    }

    const projects = p.projects
      .filter((pr) => pr.nombre.trim() || pr.descripcion.trim())
      .map((pr) =>
        [pr.nombre, pr.descripcion, pr.tecnologias ? `Tech: ${pr.tecnologias}` : '']
          .filter(Boolean)
          .join(' — '),
      );

    const email = p.email.trim() || (p.telefono.includes('@') ? p.telefono : null);

    return {
      full_name: p.nombre.trim(),
      program_slug: programSlugFromCarrera(p.carrera),
      semester: semesterMatch ? Number(semesterMatch[1]) : null,
      email,
      city: p.ciudad || 'Bogotá',
      skills: [...p.skills],
      projects,
      experience,
      languages: [...p.languages],
      education: [
        `${p.carrera} — ${p.semestre}`,
        p.universidad,
        p.resumen ? `Perfil: ${p.resumen}` : '',
        `Busca: ${p.busca}`,
        p.direccion ? `Dirección: ${p.direccion}` : '',
        p.linkedin ? `Link: ${p.linkedin}` : '',
        p.telefono ? `Tel: ${p.telefono}` : '',
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
