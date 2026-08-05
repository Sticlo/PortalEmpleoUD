import { ApiOffer, OfferCard } from './models/offer';
import { HvProfile } from './hv-profile.service';

const SOURCE_CLASS: Record<string, string> = {
  computrabajo: 'src--ct',
  elempleo: 'src--el',
  indeed: 'src--in',
  linkedin: 'src--li',
};

function sourceLabel(source: string): string {
  const map: Record<string, string> = {
    computrabajo: 'Computrabajo',
    elempleo: 'Elempleo',
    indeed: 'Indeed',
    linkedin: 'LinkedIn',
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
  if (hours < 24) return `Hace ${hours} h`;
  return 'Hace 1 día';
}

/** Encaje simple por skills de la HV vs título+descripción. */
export function scoreMatch(offer: ApiOffer, skills: string[]): number {
  if (!skills.length) return 55;
  const haystack = `${offer.title} ${offer.description}`.toLowerCase();
  let hits = 0;
  for (const skill of skills) {
    const s = skill.trim().toLowerCase();
    if (s.length >= 2 && haystack.includes(s)) hits += 1;
  }
  const ratio = hits / skills.length;
  return Math.min(95, Math.round(45 + ratio * 50));
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

  const body = [
    `${profile.busca || 'Oportunidad laboral'} enfocada en ${offer.title}.`,
    `Estudiante de ${profile.carrera} (${profile.semestre}) en ${profile.universidad}.`,
    skills.length
      ? `Experiencia práctica con ${skillLine}.`
      : 'Perfil en formación con proyectos académicos.',
    profile.cargo && profile.empresa
      ? `Experiencia reciente: ${profile.cargo} en ${profile.empresa}${profile.periodo ? ` (${profile.periodo})` : ''}.`
      : '',
    profile.logros.trim()
      ? `Logros: ${profile.logros.split('\n').map((l) => l.trim()).filter(Boolean).slice(0, 3).join('; ')}.`
      : '',
    `Interés en postularme a ${offer.company} · ${offer.city}.`,
  ]
    .filter(Boolean)
    .join(' ');

  const gap = missing.length
    ? `La oferta menciona ${missing.join(', ')} y no está en tu HV — no lo inventamos en el CV.`
    : 'Sin gaps críticos respecto a tu HV.';

  return { body, gap };
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
  return candidates.filter((c) => haystack.includes(c) && ![...have].some((h) => h.includes(c) || c.includes(h)));
}

export function toOfferCard(offer: ApiOffer, profile: HvProfile): OfferCard {
  const match = scoreMatch(offer, profile.skills);
  const { body, gap } = buildCvFromProfile(offer, profile);
  const src = offer.source.toLowerCase();
  const modality = modalityLabel(offer.modality);

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
    match,
    matchClass: matchClass(match),
    recommended: match >= 50,
    url: offer.url,
    publishedAt: offer.published_at,
    rawDescription: offer.description,
    cvTitle: `CV para: ${offer.title}`,
    cvBody: body,
    cvGap: gap,
  };
}

/** Query de búsqueda a partir de la HV (MVP Sistemas). */
export function searchQueryFromProfile(profile: HvProfile): string {
  const skills = profile.skills.map((s) => s.toLowerCase());
  if (skills.some((s) => s.includes('python'))) return 'desarrollador python';
  if (skills.some((s) => s.includes('java'))) return 'desarrollador java';
  if (skills.some((s) => /qa|playwright|selenium|test/.test(s))) return 'qa automation';
  const carrera = profile.carrera.toLowerCase();
  if (carrera.includes('sistema') || carrera.includes('software')) return 'desarrollador';
  return 'desarrollador';
}
