import { Injectable, computed, signal } from '@angular/core';

export interface HvProfile {
  nombre: string;
  contacto: string;
  ciudad: string;
  busca: string;
  universidad: string;
  carrera: string;
  semestre: string;
  cargo: string;
  empresa: string;
  periodo: string;
  logros: string;
  skills: string[];
}

export interface HvCompletenessItem {
  id: string;
  label: string;
  done: boolean;
}

const STORAGE_KEY = 'rutaud.hv.profile.v1';
const STUDENT_KEY = 'rutaud.hv.studentId';
const SAVED_KEY = 'rutaud.hv.saved';

const EMPTY_PROFILE: HvProfile = {
  nombre: '',
  contacto: '',
  ciudad: 'Bogotá',
  busca: 'Práctica profesional',
  universidad: 'Universidad Distrital Francisco José de Caldas',
  carrera: 'Ingeniería de Sistemas',
  semestre: '7º semestre',
  cargo: '',
  empresa: '',
  periodo: '',
  logros: '',
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

@Injectable({ providedIn: 'root' })
export class HvProfileService {
  readonly studentId = signal(this.loadStudentId());
  readonly profile = signal<HvProfile>(this.loadProfile());
  readonly saved = signal(this.loadSavedFlag());

  readonly statusLabel = computed(() => {
    if (!this.saved()) {
      return 'Empieza por tu HV · tarda menos de 3 minutos';
    }
    const name = this.profile().nombre.trim() || 'tu HV';
    return `HV ATS de ${name} lista · ya puedes buscar con IA`;
  });

  readonly logrosList = computed(() =>
    this.profile()
      .logros.split('\n')
      .map((l) => l.trim())
      .filter(Boolean),
  );

  readonly completenessItems = computed<HvCompletenessItem[]>(() => {
    const p = this.profile();
    return [
      { id: 'nombre', label: 'Nombre', done: !!p.nombre.trim() },
      { id: 'contacto', label: 'Contacto', done: !!p.contacto.trim() },
      { id: 'estudios', label: 'Estudios', done: !!(p.carrera && p.semestre && p.universidad) },
      {
        id: 'experiencia',
        label: 'Experiencia o logros',
        done: !!(p.cargo.trim() || p.empresa.trim() || p.logros.trim()),
      },
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
      const next = { ...p, ...partial };
      this.persistProfile(next);
      return next;
    });
    this.saved.set(false);
    this.persistSaved(false);
  }

  setSkills(skills: string[]): void {
    this.profile.update((p) => {
      const next = { ...p, skills: [...skills] };
      this.persistProfile(next);
      return next;
    });
    this.saved.set(false);
    this.persistSaved(false);
  }

  markSaved(): void {
    this.saved.set(true);
    this.persistSaved(true);
    this.persistProfile(this.profile());
  }

  resetDemoSeed(): void {
    // Solo para desarrollo: deja perfil vacío listo para llenar
    const empty = { ...EMPTY_PROFILE, skills: [] as string[] };
    this.profile.set(empty);
    this.persistProfile(empty);
    this.saved.set(false);
    this.persistSaved(false);
  }

  stepErrors(step: number): string[] {
    const p = this.profile();
    if (step === 0) {
      const e: string[] = [];
      if (!p.nombre.trim()) e.push('Escribe tu nombre completo');
      if (!p.contacto.trim()) e.push('Agrega correo o celular');
      return e;
    }
    if (step === 1) {
      const e: string[] = [];
      if (!p.universidad.trim()) e.push('Indica la universidad');
      if (!p.carrera.trim()) e.push('Elige tu carrera');
      return e;
    }
    if (step === 3) {
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
    const stored = readJson<HvProfile>(STORAGE_KEY);
    if (stored) {
      return { ...EMPTY_PROFILE, ...stored, skills: stored.skills ?? [] };
    }
    return { ...EMPTY_PROFILE, skills: [] };
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
