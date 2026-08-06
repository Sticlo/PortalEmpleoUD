import { jsPDF } from 'jspdf';
import { HvProfile } from './hv-profile.service';

/** Parte skills pegadas con comas, bullets, pipes, etc. */
export function parseSkillTokens(raw: string): string[] {
  return raw
    .split(/[,;|/·•\n\r]+/)
    .map((s) => s.replace(/\s+/g, ' ').trim())
    .filter((s) => s.length >= 1 && s.length <= 48);
}

/** Aplana skills corruptas (ej. "Python · Spring" → dos skills). */
export function sanitizeSkills(skills: string[]): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const item of skills) {
    for (const token of parseSkillTokens(String(item ?? ''))) {
      const key = token.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(token);
    }
  }
  return out;
}

function fileSlug(value: string, max = 40): string {
  return (value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-zA-Z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .toLowerCase()
    .slice(0, max);
}

/** Documento ATS plano (una columna). */
export function buildAtsDocument(p: HvProfile): string {
  const lines: string[] = [];
  const contact = [p.email, p.telefono, p.linkedin].map((x) => x.trim()).filter(Boolean);

  lines.push(p.nombre || 'HOJA DE VIDA');
  if (contact.length) lines.push(contact.join(' · '));
  lines.push(
    [p.direccion?.trim(), p.ciudad, p.busca ? `Busca: ${p.busca}` : '']
      .filter(Boolean)
      .join(' · '),
  );
  lines.push('');

  if (p.resumen.trim()) {
    lines.push('PERFIL');
    lines.push(p.resumen.trim());
    lines.push('');
  }

  lines.push('EDUCACIÓN');
  lines.push(`${p.carrera} — ${p.semestre}`);
  lines.push(p.universidad);
  lines.push('');

  const exps = p.experiences.filter(
    (e) => e.cargo.trim() || e.empresa.trim() || e.logros.trim(),
  );
  if (exps.length) {
    lines.push('EXPERIENCIA');
    for (const e of exps) {
      lines.push(`${e.cargo || 'Rol'} — ${e.empresa || 'Organización'}`);
      if (e.periodo.trim()) lines.push(e.periodo.trim());
      e.logros
        .split('\n')
        .map((l) => l.trim())
        .filter(Boolean)
        .forEach((b) => lines.push(`• ${b}`));
      lines.push('');
    }
  }

  const projs = p.projects.filter((pr) => pr.nombre.trim() || pr.descripcion.trim());
  if (projs.length) {
    lines.push('PROYECTOS');
    for (const pr of projs) {
      lines.push(pr.nombre || 'Proyecto');
      if (pr.descripcion.trim()) lines.push(pr.descripcion.trim());
      if (pr.tecnologias.trim()) lines.push(`Tecnologías: ${pr.tecnologias.trim()}`);
      lines.push('');
    }
  }

  if (p.languages.length) {
    lines.push('IDIOMAS');
    lines.push(p.languages.join(' · '));
    lines.push('');
  }

  if (p.skills.length) {
    lines.push('SKILLS');
    lines.push(sanitizeSkills(p.skills).join(' · '));
    lines.push('');
  }

  return lines.join('\n').trim() + '\n';
}

/** HV completa adaptada a una oferta (header + cuerpo editable). Sin notas internas. */
export function buildAdaptedAtsDocument(
  p: HvProfile,
  opts: { offerTitle: string; company: string; body: string },
): string {
  const lines: string[] = [];
  const contact = [p.email, p.telefono, p.linkedin].map((x) => x.trim()).filter(Boolean);

  lines.push(p.nombre || 'HOJA DE VIDA');
  if (contact.length) lines.push(contact.join(' · '));
  lines.push(
    [p.direccion?.trim(), p.ciudad, p.busca ? `Busca: ${p.busca}` : '']
      .filter(Boolean)
      .join(' · '),
  );
  lines.push('');

  const body = (opts.body || '').trim();
  if (body) {
    // Si el cuerpo ya trae nombre/contacto, usamos solo el cuerpo
    const looksComplete =
      body.split('\n')[0]?.toLowerCase().includes((p.nombre || '').toLowerCase().split(' ')[0] || '___') ||
      /^(PERFIL|EDUCACI[OÓ]N|EXPERIENCIA|SKILLS)/im.test(body);
    if (looksComplete && body.length > 80) {
      return `${body.trim()}\n`;
    }
    lines.push(body);
  } else {
    lines.push(buildAtsDocument(p).trim());
  }

  return lines.join('\n').trim() + '\n';
}

const SECTION_RE =
  /^(PERFIL|PERFIL PROFESIONAL|EDUCACI[OÓ]N|EXPERIENCIA|EXPERIENCIA LABORAL|PROYECTOS|SKILLS|HABILIDADES|IDIOMAS|FORMACI[OÓ]N)\s*:?\s*$/i;

/**
 * Genera un PDF ATS (texto seleccionable, tipografía limpia, títulos en rojo UD).
 * Usa el texto ya editado en pantalla.
 */
export function downloadAtsPdf(text: string, filename: string): void {
  const doc = new jsPDF({ unit: 'pt', format: 'a4', compress: true });
  const pageW = doc.internal.pageSize.getWidth();
  const pageH = doc.internal.pageSize.getHeight();
  const marginX = 48;
  const marginY = 48;
  const maxW = pageW - marginX * 2;
  const UD_RED: [number, number, number] = [148, 20, 16];
  const MUTED: [number, number, number] = [92, 92, 92];
  const BLACK: [number, number, number] = [26, 26, 26];

  let y = marginY;
  let isFirstContent = true;

  const ensureSpace = (need: number) => {
    if (y + need > pageH - marginY) {
      doc.addPage();
      y = marginY;
    }
  };

  const writeWrapped = (
    content: string,
    opts: { size: number; style: 'normal' | 'bold'; color: [number, number, number]; gap?: number },
  ) => {
    doc.setFont('helvetica', opts.style);
    doc.setFontSize(opts.size);
    doc.setTextColor(...opts.color);
    const lines = doc.splitTextToSize(content, maxW) as string[];
    const leading = opts.size * 1.35;
    for (const line of lines) {
      ensureSpace(leading);
      doc.text(line, marginX, y);
      y += leading;
    }
    y += opts.gap ?? 4;
  };

  const clean = text
    .replace(/\r\n/g, '\n')
    .split('\n')
    .map((l) => l.replace(/\s+$/g, ''))
    .filter((l, i, arr) => !(l.trim() === '' && arr[i - 1]?.trim() === ''))
    .filter((l) => !l.trim().startsWith('---'))
    .filter((l) => !/^Adaptada para:/i.test(l.trim()))
    .filter((l) => !/^Generado con RutaUD/i.test(l.trim()));

  for (const raw of clean) {
    const line = raw.trim();
    if (!line) {
      y += 8;
      continue;
    }

    if (SECTION_RE.test(line)) {
      y += 10;
      ensureSpace(28);
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(11);
      doc.setTextColor(...UD_RED);
      doc.text(line.toUpperCase().replace(/:$/, ''), marginX, y);
      y += 6;
      doc.setDrawColor(217, 217, 217);
      doc.setLineWidth(0.8);
      doc.line(marginX, y, marginX + maxW, y);
      y += 14;
      isFirstContent = false;
      continue;
    }

    if (isFirstContent) {
      writeWrapped(line, { size: 20, style: 'bold', color: BLACK, gap: 6 });
      isFirstContent = false;
      continue;
    }

    // Meta / contacto
    if (
      line.includes('@') ||
      /^https?:\/\//i.test(line) ||
      /Busca:/i.test(line) ||
      /Bogot[aá]/i.test(line)
    ) {
      writeWrapped(line, { size: 10, style: 'normal', color: MUTED, gap: 3 });
      continue;
    }

    if (line.startsWith('•') || line.startsWith('-') || line.startsWith('*')) {
      const bullet = `• ${line.replace(/^([•\-*]\s*)/, '')}`;
      writeWrapped(bullet, { size: 10.5, style: 'normal', color: BLACK, gap: 2 });
      continue;
    }

    // Título de cargo / proyecto (línea con "—")
    if (line.includes('—') || line.includes(' - ')) {
      writeWrapped(line, { size: 11, style: 'bold', color: BLACK, gap: 2 });
      continue;
    }

    writeWrapped(line, { size: 10.5, style: 'normal', color: BLACK, gap: 3 });
  }

  const safeName = filename.endsWith('.pdf') ? filename : `${filename}.pdf`;
  doc.save(safeName);
}

export function downloadAtsPdfFromProfile(profile: HvProfile): void {
  const text = buildAtsDocument(profile);
  const slug = fileSlug(profile.nombre || 'hv-ats');
  downloadAtsPdf(text, `${slug || 'hv-ats'}-rutaud.pdf`);
}

export function downloadAdaptedAtsPdf(
  profile: HvProfile,
  opts: { offerTitle: string; company: string; body: string },
): void {
  const text = buildAdaptedAtsDocument(profile, opts);
  const nameSlug = fileSlug(profile.nombre || 'hv', 24);
  const offerSlug = fileSlug(opts.offerTitle || 'oferta', 28);
  downloadAtsPdf(text, `${nameSlug || 'hv'}-${offerSlug || 'oferta'}-ats.pdf`);
}

/** @deprecated usar downloadAtsPdfFromProfile */
export function downloadAtsTxt(profile: HvProfile): void {
  downloadAtsPdfFromProfile(profile);
}

/** @deprecated usar downloadAdaptedAtsPdf */
export function downloadAdaptedAtsTxt(
  profile: HvProfile,
  opts: { offerTitle: string; company: string; body: string },
): void {
  downloadAdaptedAtsPdf(profile, opts);
}
