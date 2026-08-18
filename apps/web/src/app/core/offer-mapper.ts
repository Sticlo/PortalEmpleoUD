import { ApiOffer, OfferCard } from './models/offer';
import { HvProfile } from './hv-profile.service';

const SOURCE_CLASS: Record<string, string> = {
  computrabajo: 'src--ct',
  elempleo: 'src--el',
  indeed: 'src--in',
  linkedin: 'src--li',
  empresa: 'src--empresa',
  'empleos-de-hoy': 'src--hoy',
};

type CareerFamily =
  | 'sistemas'
  | 'civil'
  | 'catastral'
  | 'electronica'
  | 'forestal'
  | 'quimica'
  | 'industrial'
  | 'artes'
  | 'otra';

const CAREER_PATTERNS: Record<CareerFamily, RegExp[]> = {
  sistemas: [
    /sistema/,
    /software/,
    /desarroll/,
    /programad/,
    /backend/,
    /frontend/,
    /full\s*stack/,
    /\bqa\b/,
    /datos/,
    /data/,
    /devops/,
    /inform[aá]tica/,
    /computaci/,
  ],
  catastral: [
    /catastr/,
    /geodes/,
    /predial/,
    /topograf/,
    /cartograf/,
    /fotogrametr/,
    /\bgis\b/,
    /georreferenc/,
  ],
  civil: [/civil/, /estructur/, /cimentac/, /obra\b/, /residente/, /vial/],
  electronica: [/electr[oó]n/, /\biot\b/, /embebido/, /hardware/, /circuito/],
  forestal: [/forestal/, /ecol[oó]g/, /silvicult/, /ambiental/],
  quimica: [/qu[ií]mic/, /laboratorio/, /procesos qu[ií]m/],
  industrial: [/industrial/, /log[ií]stica/, /producci[oó]n/, /calidad/],
  artes: [/artes/, /docente/, /expresi[oó]n/, /taller art/, /mediaci[oó]n cultural/],
  otra: [],
};

function sourceLabel(source: string): string {
  const map: Record<string, string> = {
    computrabajo: 'Computrabajo',
    elempleo: 'Elempleo',
    indeed: 'Indeed',
    linkedin: 'LinkedIn',
    empresa: 'Empresa',
    'empleos-de-hoy': 'Empleos de hoy',
  };
  return map[source.toLowerCase()] ?? source;
}

function modalityLabel(modality: string): string {
  const m = modality.toLowerCase();
  if (m.includes('hibr') || m.includes('híbr')) return 'Híbrido';
  if (m.includes('remoto')) return 'Remoto';
  if (m.includes('presencial')) return 'Presencial';
  return modality || 'Sin modalidad';
}

export function formatFresh(publishedAt: string): string {
  const published = new Date(publishedAt);
  if (Number.isNaN(published.getTime())) return 'Reciente';
  const hours = Math.max(0, Math.round((Date.now() - published.getTime()) / 3_600_000));
  if (hours < 1) return 'Hace minutos';
  if (hours === 1) return 'Hace 1 h';
  // Dentro de ~36 h mostramos horas (22 h, 24 h), no “1 día”
  if (hours <= 36) return `Hace ${hours} h`;
  const days = Math.max(1, Math.round(hours / 24));
  if (days === 1) return 'Hace 1 día';
  return `Hace ${days} días`;
}

function detectOfferCareer(haystack: string, programTags: string[] = []): CareerFamily {
  const tags = programTags.join(' ').toLowerCase();
  const blob = `${haystack} ${tags}`;
  const order: CareerFamily[] = [
    'catastral',
    'civil',
    'electronica',
    'forestal',
    'quimica',
    'artes',
    'industrial',
    'sistemas',
  ];
  for (const family of order) {
    if (CAREER_PATTERNS[family].some((re) => re.test(blob))) return family;
  }
  return 'otra';
}

function detectProfileCareer(profile: HvProfile): CareerFamily {
  const carrera = profile.carrera.toLowerCase();
  const skills = profile.skills.join(' ').toLowerCase();
  const blob = `${carrera} ${skills} ${profile.resumen}`.toLowerCase();

  if (/catastr|geodes/.test(carrera)) return 'catastral';
  if (/civil/.test(carrera)) return 'civil';
  if (/electr/.test(carrera)) return 'electronica';
  if (/forestal|ambiental/.test(carrera)) return 'forestal';
  if (/qu[ií]mic/.test(carrera)) return 'quimica';
  if (/industrial/.test(carrera)) return 'industrial';
  if (/artes|licenciatura/.test(carrera)) return 'artes';
  if (/sistema|software|datos|telem[aá]tica|inform[aá]tica/.test(carrera)) return 'sistemas';

  // Inferencia por skills si la carrera es "Otra"
  if (CAREER_PATTERNS.sistemas.some((re) => re.test(blob)) || /python|angular|java|react|\.net|sql/.test(skills)) {
    return 'sistemas';
  }
  return 'otra';
}

function careerFamilyLabel(f: CareerFamily): string {
  const map: Record<CareerFamily, string> = {
    sistemas: 'Sistemas / software',
    catastral: 'Catastral / geodesia',
    civil: 'Ingeniería Civil',
    electronica: 'Electrónica',
    forestal: 'Forestal / ambiental',
    quimica: 'Química',
    industrial: 'Industrial',
    artes: 'Artes',
    otra: 'otra área',
  };
  return map[f];
}

/**
 * Encaje honesto: skills + carrera.
 * Civil vs HV de sistemas → % bajo (no ~45% por defecto).
 */
export function scoreMatch(offer: ApiOffer, profile: HvProfile): number {
  const haystack = `${offer.title} ${offer.description}`.toLowerCase();
  const offerCareer = detectOfferCareer(haystack, offer.program_tags || []);
  const profileCareer = detectProfileCareer(profile);
  const skills = profile.skills.filter(Boolean);

  let hits = 0;
  for (const skill of skills) {
    const s = skill.trim().toLowerCase();
    if (s.length >= 2 && haystack.includes(s)) hits += 1;
  }
  const ratio = skills.length ? hits / skills.length : 0;

  const careerMismatch =
    offerCareer !== 'otra' &&
    profileCareer !== 'otra' &&
    offerCareer !== profileCareer;

  if (careerMismatch) {
    // Máx ~22%: deja claro que no es tu carrera, sin llegar a 0 absurdo
    return Math.min(22, Math.max(8, Math.round(8 + ratio * 14)));
  }

  if (!skills.length) return 40;
  return Math.min(95, Math.round(40 + ratio * 55));
}

/** Texto corto para el Ojo cuando hay choque de carrera. */
export function careerMismatchNote(offer: ApiOffer, profile: HvProfile): string | null {
  const haystack = `${offer.title} ${offer.description}`.toLowerCase();
  const offerCareer = detectOfferCareer(haystack, offer.program_tags || []);
  const profileCareer = detectProfileCareer(profile);
  if (
    offerCareer === 'otra' ||
    profileCareer === 'otra' ||
    offerCareer === profileCareer
  ) {
    return null;
  }
  return (
    `Esta vacante apunta a ${careerFamilyLabel(offerCareer)}, y tu HV es de ` +
    `${careerFamilyLabel(profileCareer)}. El encaje bajo es intencional: puedes preparar el CV igual, ` +
    `pero el Ojo te avisa que el perfil no es el natural para esta oferta.`
  );
}

function matchClass(score: number): OfferCard['matchClass'] {
  if (score >= 75) return 'match--high';
  if (score >= 55) return 'match--mid';
  return 'match--low';
}

export function buildCvFromProfile(offer: ApiOffer, profile: HvProfile): { body: string; gap: string } {
  const skills = profile.skills.filter(Boolean);
  const skillLine = skills.length ? skills.join(', ') : 'las herramientas de tu formación';
  const haystack = `${offer.title} ${offer.description}`.toLowerCase();
  const missing = commonGaps(haystack, skills);
  const careerNote = careerMismatchNote(offer, profile);

  const exp = profile.experiences.find(
    (e) => e.cargo.trim() || e.empresa.trim() || e.logros.trim(),
  );
  const logros = exp
    ? exp.logros
        .split('\n')
        .map((l) => l.trim())
        .filter(Boolean)
        .slice(0, 3)
    : [];

  const body = [
    profile.resumen.trim() || `${profile.busca || 'Oportunidad laboral'} enfocada en ${offer.title}.`,
    `Estudiante de ${profile.carrera} (${profile.semestre}) en ${profile.universidad}.`,
    skills.length
      ? `Experiencia práctica con ${skillLine}.`
      : 'Perfil en formación con proyectos académicos.',
    exp && (exp.cargo || exp.empresa)
      ? `Experiencia reciente: ${exp.cargo} en ${exp.empresa}${exp.periodo ? ` (${exp.periodo})` : ''}.`
      : '',
    logros.length ? `Logros: ${logros.join('; ')}.` : '',
    `Interés en postularme a ${offer.company} · ${offer.city}.`,
  ]
    .filter(Boolean)
    .join(' ');

  const parts: string[] = [];
  if (careerNote) parts.push(careerNote);
  if (missing.length) {
    parts.push(
      `La oferta menciona ${missing.join(', ')} y no está en tu HV — no lo inventamos en el CV.`,
    );
  } else if (!careerNote) {
    parts.push('Sin gaps críticos respecto a tu HV.');
  }

  return { body, gap: parts.join(' ') };
}

function commonGaps(haystack: string, skills: string[]): string[] {
  const have = new Set(skills.map((s) => s.toLowerCase()));
  const candidates = [
    'docker',
    'kubernetes',
    'react',
    'angular',
    'java',
    'spring',
    'aws',
    'azure',
    'linux',
    'node',
    'typescript',
    'power bi',
  ];
  return candidates.filter(
    (c) => haystack.includes(c) && ![...have].some((h) => h.includes(c) || c.includes(h)),
  );
}

export function toOfferCard(offer: ApiOffer, profile: HvProfile): OfferCard {
  const match = scoreMatch(offer, profile);
  const { body, gap } = buildCvFromProfile(offer, profile);
  const src = offer.source.toLowerCase();
  const modality = modalityLabel(offer.modality);
  const programLabel =
    offer.program_tags?.find((t) => t.includes(' ') || t.includes('Ingenier') || t.includes('Licenc')) ||
    offer.program_tags?.[1] ||
    offer.program_tags?.[0] ||
    '';

  return {
    id: offer.id,
    source: sourceLabel(offer.source),
    sourceClass: SOURCE_CLASS[src] ?? 'src--ct',
    fresh: formatFresh(offer.published_at),
    title: offer.title,
    company: offer.company,
    companyLine: `${offer.company} · ${offer.city} · ${modality}`,
    city: offer.city,
    modality: offer.modality,
    modalityLabel: modality,
    salary: (offer.salary || '').trim(),
    description: offer.description || 'Sin descripción detallada en el portal.',
    programLabel,
    match,
    matchClass: matchClass(match),
    // Nunca bloqueamos Preparar CV: el Ojo explica la afinidad baja
    recommended: true,
    url: offer.url,
    publishedAt: offer.published_at,
    rawDescription: offer.description,
    cvTitle: `CV para: ${offer.title}`,
    cvBody: body,
    cvGap: gap,
  };
}

/** Query de búsqueda a partir de la HV. */
export function searchQueryFromProfile(profile: HvProfile): string {
  const skills = profile.skills.map((s) => s.toLowerCase());
  if (skills.some((s) => s.includes('python'))) return 'desarrollador python';
  if (skills.some((s) => s.includes('java'))) return 'desarrollador java';
  if (skills.some((s) => /qa|playwright|selenium|test/.test(s))) return 'qa automation';
  const carrera = profile.carrera.toLowerCase();
  if (carrera.includes('catastr') || carrera.includes('geodes')) return 'ingeniero catastral';
  if (carrera.includes('civil')) return 'ingeniero civil';
  if (carrera.includes('electr')) return 'ingeniero electronico';
  if (carrera.includes('sistema') || carrera.includes('software') || carrera.includes('datos')) {
    return 'desarrollador';
  }
  return 'desarrollador';
}
