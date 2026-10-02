import { Injectable, computed, signal } from '@angular/core';
import { sanitizeSkills } from './hv-ats-export';

export interface HvExperience {
  id: string;
  cargo: string;
  empresa: string;
  periodo: string;
  /** Una línea = un bullet ATS */
  logros: string;
}

export interface HvProject {
  id: string;
  nombre: string;
  descripcion: string;
  tecnologias: string;
}

export interface HvProfile {
  nombre: string;
  email: string;
  telefono: string;
  linkedin: string;
  ciudad: string;
  /** Dirección / barrio donde vive (ATS) */
  direccion: string;
  busca: string;
  /** Perfil profesional corto (2–4 líneas ATS) */
  resumen: string;
  universidad: string;
  carrera: string;
  semestre: string;
  experiences: HvExperience[];
  projects: HvProject[];
  languages: string[];
  skills: string[];
}

export interface HvCompletenessItem {
  id: string;
  label: string;
  done: boolean;
}

const STORAGE_KEY = 'rutaud.hv.profile.v2';
const LEGACY_KEY = 'rutaud.hv.profile.v1';
const STUDENT_KEY = 'rutaud.hv.studentId';
const SAVED_KEY = 'rutaud.hv.saved';

function uid(prefix: string): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `${prefix}-${crypto.randomUUID().slice(0, 8)}`;
  }
  return `${prefix}-${Date.now().toString(36)}`;
}

export function emptyExperience(): HvExperience {
  return { id: uid('exp'), cargo: '', empresa: '', periodo: '', logros: '' };
}

export function emptyProject(): HvProject {
  return { id: uid('proj'), nombre: '', descripcion: '', tecnologias: '' };
}

const EMPTY_PROFILE: HvProfile = {
  nombre: '',
  email: '',
  telefono: '',
  linkedin: '',
  ciudad: 'Bogotá',
  direccion: '',
  busca: 'Práctica profesional',
  resumen: '',
  universidad: 'Universidad Distrital Francisco José de Caldas',
  carrera: 'Ingeniería de Sistemas',
  semestre: '7º semestre',
  experiences: [emptyExperience()],
  projects: [],
  languages: [],
  skills: [],
};

function newStudentId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `ud-${crypto.randomUUID().slice(0, 8)}`;
  }
  return `ud-${Date.now().toString(36)}`;
}

function readJson<T>(key: string): T | null {
  try {
    if (typeof localStorage === 'undefined') return null;
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

/** Migra HV v1 (un solo bloque) → v2. */
function migrateFromV1(raw: Record<string, unknown>): HvProfile {
  const contacto = String(raw['contacto'] ?? '');
  let email = '';
  let telefono = '';
  if (contacto.includes('@')) {
    email = contacto.split(/[·,|]/)[0].trim();
    const rest = contacto.replace(email, '').replace(/^[·,\s|]+/, '').trim();
    telefono = rest;
  } else {
    telefono = contacto.trim();
  }

  const cargo = String(raw['cargo'] ?? '');
  const empresa = String(raw['empresa'] ?? '');
  const periodo = String(raw['periodo'] ?? '');
  const logros = String(raw['logros'] ?? '');
  const hasExp = !!(cargo || empresa || logros);

  return {
    ...EMPTY_PROFILE,
    nombre: String(raw['nombre'] ?? ''),
    email,
    telefono,
    ciudad: String(raw['ciudad'] ?? 'Bogotá'),
    direccion: String(raw['direccion'] ?? ''),
    busca: String(raw['busca'] ?? 'Práctica profesional'),
    universidad: String(raw['universidad'] ?? EMPTY_PROFILE.universidad),
    carrera: String(raw['carrera'] ?? EMPTY_PROFILE.carrera),
    semestre: String(raw['semestre'] ?? EMPTY_PROFILE.semestre),
    skills: Array.isArray(raw['skills']) ? (raw['skills'] as string[]) : [],
    experiences: hasExp
      ? [{ id: uid('exp'), cargo, empresa, periodo, logros }]
      : [emptyExperience()],
    projects: [],
    languages: [],
    resumen: '',
    linkedin: '',
  };
}

function normalizeProfile(raw: Partial<HvProfile> & Record<string, unknown>): HvProfile {
  const experiences =
    Array.isArray(raw.experiences) && raw.experiences.length
      ? raw.experiences.map((e) => ({
          id: e.id || uid('exp'),
          cargo: e.cargo || '',
          empresa: e.empresa || '',
          periodo: e.periodo || '',
          logros: e.logros || '',
        }))
      : [emptyExperience()];

  const projects = Array.isArray(raw.projects)
    ? raw.projects.map((p) => ({
        id: p.id || uid('proj'),
        nombre: p.nombre || '',
        descripcion: p.descripcion || '',
        tecnologias: p.tecnologias || '',
      }))
    : [];

  return {
    ...EMPTY_PROFILE,
    ...raw,
    direccion: String(raw.direccion ?? ''),
    experiences,
    projects,
    languages: Array.isArray(raw.languages) ? [...raw.languages] : [],
    skills: Array.isArray(raw.skills) ? sanitizeSkills(raw.skills as string[]) : [],
  } as HvProfile;
}

@Injectable({ providedIn: 'root' })
export class HvProfileService {
  readonly studentId = signal(this.loadStudentId());
  readonly profile = signal<HvProfile>(this.loadProfile());
  readonly saved = signal(this.loadSavedFlag());

  readonly statusLabel = computed(() => {
    if (!this.saved()) {
      return 'Empieza por tu HV · tarda menos de 5 minutos';
    }
    const name = this.profile().nombre.trim() || 'tu HV';
    return `HV ATS de ${name} lista · ya puedes buscar con IA`;
  });

  readonly contactLine = computed(() => {
    const p = this.profile();
    return [p.email, p.telefono, p.linkedin].map((x) => x.trim()).filter(Boolean).join(' · ');
  });

  readonly completenessItems = computed<HvCompletenessItem[]>(() => {
    const p = this.profile();
    const hasContact = !!(p.email.trim() || p.telefono.trim());
    const hasExp = p.experiences.some(
      (e) => e.cargo.trim() || e.empresa.trim() || e.logros.trim(),
    );
    const hasProj = p.projects.some((pr) => pr.nombre.trim() || pr.descripcion.trim());
    return [
      { id: 'nombre', label: 'Nombre', done: !!p.nombre.trim() },
      { id: 'contacto', label: 'Contacto', done: hasContact },
      { id: 'resumen', label: 'Perfil ATS', done: p.resumen.trim().length >= 40 },
      { id: 'estudios', label: 'Estudios', done: !!(p.carrera && p.semestre && p.universidad) },
      { id: 'experiencia', label: 'Experiencia o proyectos', done: hasExp || hasProj },
      { id: 'skills', label: 'Al menos 3 skills', done: p.skills.length >= 3 },
    ];
  });

  readonly completenessPct = computed(() => {
    const items = this.completenessItems();
    const done = items.filter((i) => i.done).length;
    return Math.round((done / items.length) * 100);
  });

  readonly isCompleteEnough = computed(() => this.completenessPct() >= 80);

  patch(partial: Partial<HvProfile>): void {
    this.profile.update((p) => {
      const next = normalizeProfile({ ...p, ...partial });
      this.persistProfile(next);
      return next;
    });
    this.saved.set(false);
    this.persistSaved(false);
  }

  setSkills(skills: string[]): void {
    this.patch({ skills: sanitizeSkills(skills) });
  }

  setLanguages(languages: string[]): void {
    this.patch({ languages: [...languages] });
  }

  addExperience(): void {
    this.patch({ experiences: [...this.profile().experiences, emptyExperience()] });
  }

  updateExperience(id: string, partial: Partial<HvExperience>): void {
    this.patch({
      experiences: this.profile().experiences.map((e) =>
        e.id === id ? { ...e, ...partial } : e,
      ),
    });
  }

  removeExperience(id: string): void {
    const list = this.profile().experiences.filter((e) => e.id !== id);
    this.patch({ experiences: list.length ? list : [emptyExperience()] });
  }

  addProject(): void {
    this.patch({ projects: [...this.profile().projects, emptyProject()] });
  }

  updateProject(id: string, partial: Partial<HvProject>): void {
    this.patch({
      projects: this.profile().projects.map((p) => (p.id === id ? { ...p, ...partial } : p)),
    });
  }

  removeProject(id: string): void {
    this.patch({ projects: this.profile().projects.filter((p) => p.id !== id) });
  }

  markSaved(): void {
    this.saved.set(true);
    this.persistSaved(true);
    this.persistProfile(this.profile());
  }

  resetDemoSeed(): void {
    const empty = normalizeProfile({ ...EMPTY_PROFILE, experiences: [emptyExperience()] });
    this.profile.set(empty);
    this.persistProfile(empty);
    this.saved.set(false);
    this.persistSaved(false);
  }

  /** Borra la HV de este navegador y genera un identificador nuevo. */
  clearLocalData(): void {
    try {
      for (const key of [STORAGE_KEY, LEGACY_KEY, SAVED_KEY, STUDENT_KEY]) {
        localStorage?.removeItem(key);
      }
    } catch {
      /* SSR / private */
    }
    this.resetDemoSeed();
    this.studentId.set(this.loadStudentId());
  }

  stepErrors(step: number): string[] {
    const p = this.profile();
    if (step === 0) {
      const e: string[] = [];
      if (!p.nombre.trim()) e.push('Escribe tu nombre completo');
      if (!p.email.trim() && !p.telefono.trim()) e.push('Agrega correo o celular');
      return e;
    }
    if (step === 1) {
      const e: string[] = [];
      if (!p.universidad.trim()) e.push('Indica la universidad');
      if (!p.carrera.trim()) e.push('Escribe el nombre de tu carrera');
      return e;
    }
    if (step === 4) {
      if (p.skills.length < 3) return ['Agrega al menos 3 skills reales'];
    }
    return [];
  }

  private loadStudentId(): string {
    const existing = typeof localStorage !== 'undefined' ? localStorage.getItem(STUDENT_KEY) : null;
    if (existing) return existing;
    const id = newStudentId();
    try {
      localStorage?.setItem(STUDENT_KEY, id);
    } catch {
      /* SSR / private */
    }
    return id;
  }

  private loadProfile(): HvProfile {
    const v2 = readJson<Partial<HvProfile>>(STORAGE_KEY);
    if (v2) return normalizeProfile(v2 as Partial<HvProfile> & Record<string, unknown>);

    const v1 = readJson<Record<string, unknown>>(LEGACY_KEY);
    if (v1) {
      const migrated = migrateFromV1(v1);
      this.persistProfile(migrated);
      return migrated;
    }
    return normalizeProfile({ ...EMPTY_PROFILE });
  }

  private loadSavedFlag(): boolean {
    try {
      return localStorage?.getItem(SAVED_KEY) === '1';
    } catch {
      return false;
    }
  }

  private persistProfile(profile: HvProfile): void {
    try {
      localStorage?.setItem(STORAGE_KEY, JSON.stringify(profile));
    } catch {
      /* ignore */
    }
  }

  private persistSaved(saved: boolean): void {
    try {
      localStorage?.setItem(SAVED_KEY, saved ? '1' : '0');
    } catch {
      /* ignore */
    }
  }
}
