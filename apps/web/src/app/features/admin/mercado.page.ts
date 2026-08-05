import { isPlatformBrowser } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  Component,
  Inject,
  OnInit,
  PLATFORM_ID,
  computed,
  inject,
  signal,
} from '@angular/core';
import { ChartConfiguration } from 'chart.js';
import { firstValueFrom } from 'rxjs';
import { MarketChartComponent, MarketChartOptions } from './market-chart.component';

export interface MarketSampleOffer {
  title: string;
  company: string;
  source: string;
  salary?: string | null;
  applicants?: number | null;
  url?: string | null;
}

export interface MarketSkillStat {
  skill: string;
  count: number;
  percent: number;
  previous_count: number;
  trend: 'sube' | 'baja' | 'estable' | 'nueva';
  samples: MarketSampleOffer[];
}

export interface MarketDistributionItem {
  label: string;
  count: number;
  percent: number;
}

export interface MarketTitleStat {
  title: string;
  count: number;
  percent: number;
}

export interface MarketCompetitionStat {
  offers_with_applicants: number;
  offers_total: number;
  coverage_percent: number;
  avg_applicants: number | null;
  median_applicants: number | null;
  max_applicants: number | null;
  note: string;
}

export interface MarketStatsResponse {
  days: number;
  total_offers: number;
  archive_total: number;
  top_skills: MarketSkillStat[];
  low_demand_skills: MarketSkillStat[];
  top_titles: MarketTitleStat[];
  top_companies: MarketDistributionItem[];
  by_modality: MarketDistributionItem[];
  by_source: MarketDistributionItem[];
  by_program: MarketDistributionItem[];
  by_city: MarketDistributionItem[];
  by_seniority: MarketDistributionItem[];
  salary_bands: MarketDistributionItem[];
  salary_disclosed_percent: number;
  competition: MarketCompetitionStat;
  insight: string;
  applicants_disclaimer: string;
}

export interface MarketHarvestResponse {
  ok: boolean;
  unique: number;
  newly_archived: number;
  archive_total: number;
  note: string;
}

/** Paleta institucional UD (sin violeta genérico). */
const PALETTE = [
  '#941410',
  '#c45c3e',
  '#2d2d2d',
  '#1b6b3a',
  '#9a6b00',
  '#4a6fa5',
  '#6b4c3b',
  '#8a3030',
  '#5c5c5c',
  '#3d5a4c',
  '#b08968',
  '#264653',
];

const TREND_LABEL: Record<string, string> = {
  sube: '▲ sube',
  baja: '▼ baja',
  estable: '— estable',
  nueva: '★ nueva',
};

function colors(n: number): string[] {
  return Array.from({ length: n }, (_, i) => PALETTE[i % PALETTE.length]);
}

@Component({
  selector: 'app-mercado-page',
  imports: [MarketChartComponent],
  templateUrl: './mercado.page.html',
})
export class MercadoPage implements OnInit {
  readonly loading = signal(true);
  readonly refreshing = signal(false);
  readonly error = signal('');
  readonly toast = signal('');
  readonly stats = signal<MarketStatsResponse | null>(null);
  readonly days = signal(30);
  readonly selectedSkill = signal<MarketSkillStat | null>(null);

  readonly skillsBar = computed(() => this.buildSkillsBar(this.stats()));
  readonly programDonut = computed(() => this.buildDonut(this.stats()?.by_program ?? [], 'Carreras'));
  readonly modalityDonut = computed(() => this.buildDonut(this.stats()?.by_modality ?? [], 'Modalidad'));
  readonly seniorityDonut = computed(() => this.buildDonut(this.stats()?.by_seniority ?? [], 'Nivel'));
  readonly sourceDonut = computed(() => this.buildDonut(this.stats()?.by_source ?? [], 'Portales'));
  readonly companiesBar = computed(() => this.buildHBar(this.stats()?.top_companies ?? [], 'Empresas'));
  readonly titlesBar = computed(() => this.buildHBar(
    (this.stats()?.top_titles ?? []).map((t) => ({
      label: t.title.length > 36 ? t.title.slice(0, 34) + '…' : t.title,
      count: t.count,
      percent: t.percent,
    })),
    'Cargos',
  ));
  readonly salaryBar = computed(() => this.buildVBar(this.stats()?.salary_bands ?? [], 'Salarios'));
  readonly lowSkillsBar = computed(() =>
    this.buildHBar(
      (this.stats()?.low_demand_skills ?? [])
        .slice(0, 8)
        .map((s) => ({ label: s.skill, count: s.count, percent: s.percent })),
      'Poco pedidas',
    ),
  );

  readonly barOpts: MarketChartOptions = {
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#212529',
        titleFont: { family: 'Source Sans 3', size: 13 },
        bodyFont: { family: 'Source Sans 3', size: 12 },
        padding: 10,
      },
    },
    scales: {
      x: {
        grid: { color: 'rgba(0,0,0,0.05)' },
        ticks: { font: { family: 'Source Sans 3', size: 11 }, color: '#5c5c5c' },
      },
      y: {
        grid: { display: false },
        ticks: { font: { family: 'Source Sans 3', size: 11 }, color: '#2d2d2d' },
      },
    },
  };

  readonly hBarOpts: MarketChartOptions = {
    indexAxis: 'y',
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#212529',
        titleFont: { family: 'Source Sans 3', size: 13 },
        bodyFont: { family: 'Source Sans 3', size: 12 },
      },
    },
    scales: {
      x: {
        beginAtZero: true,
        grid: { color: 'rgba(0,0,0,0.05)' },
        ticks: { font: { family: 'Source Sans 3', size: 11 }, color: '#5c5c5c', precision: 0 },
      },
      y: {
        grid: { display: false },
        ticks: { font: { family: 'Source Sans 3', size: 11 }, color: '#2d2d2d' },
      },
    },
  };

  readonly donutOpts: MarketChartOptions = {
    cutout: '58%',
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          boxWidth: 12,
          padding: 12,
          font: { family: 'Source Sans 3', size: 12 },
          color: '#2d2d2d',
        },
      },
      tooltip: {
        backgroundColor: '#212529',
        callbacks: {
          label: (ctx: { parsed: number; label?: string; dataset: { data: number[] } }) => {
            const v = Number(ctx.parsed) || 0;
            const sum = (ctx.dataset.data || []).reduce((a, b) => a + b, 0) || 1;
            return ` ${ctx.label}: ${v} (${Math.round((v * 100) / sum)}%)`;
          },
        },
      },
    },
  };

  private readonly http = inject(HttpClient);

  constructor(@Inject(PLATFORM_ID) private readonly platformId: object) {}

  ngOnInit(): void {
    if (isPlatformBrowser(this.platformId)) {
      void this.load();
    }
  }

  async load(days?: number): Promise<void> {
    if (days) this.days.set(days);
    this.loading.set(true);
    this.error.set('');
    this.selectedSkill.set(null);
    try {
      const res = await firstValueFrom(
        this.http.get<MarketStatsResponse>(`/api/v1/stats/market?days=${this.days()}`),
      );
      this.stats.set(res);
      if (res.top_skills[0]) this.selectedSkill.set(res.top_skills[0]);
    } catch {
      this.error.set('No se pudieron cargar las métricas. ¿La API está en :8000?');
    } finally {
      this.loading.set(false);
    }
  }

  async refreshMarket(): Promise<void> {
    this.refreshing.set(true);
    this.toast.set('Trayendo vacantes reales de los portales (1–3 min)…');
    try {
      const res = await firstValueFrom(
        this.http.post<MarketHarvestResponse>('/api/v1/stats/market/refresh', {}),
      );
      this.toast.set(
        `Listo: ${res.newly_archived} nuevas · ${res.unique} únicas · histórico ${res.archive_total}`,
      );
      await this.load();
    } catch {
      this.toast.set('Falló la actualización. Revisa la API / red.');
    } finally {
      this.refreshing.set(false);
    }
  }

  pickSkill(skill: MarketSkillStat): void {
    this.selectedSkill.set(skill);
  }

  trendLabel(trend: string): string {
    return TREND_LABEL[trend] ?? trend;
  }

  private buildSkillsBar(s: MarketStatsResponse | null): ChartConfiguration['data'] {
    const skills = (s?.top_skills ?? []).slice(0, 12);
    return {
      labels: skills.map((x) => x.skill),
      datasets: [
        {
          label: 'Vacantes',
          data: skills.map((x) => x.count),
          backgroundColor: colors(skills.length),
          borderRadius: 4,
          borderSkipped: false,
          maxBarThickness: 28,
        },
      ],
    };
  }

  private buildDonut(
    items: MarketDistributionItem[],
    _label: string,
  ): ChartConfiguration['data'] {
    return {
      labels: items.map((i) => i.label),
      datasets: [
        {
          data: items.map((i) => i.count),
          backgroundColor: colors(items.length),
          borderWidth: 2,
          borderColor: '#ffffff',
          hoverOffset: 6,
        },
      ],
    };
  }

  private buildHBar(
    items: MarketDistributionItem[],
    _label: string,
  ): ChartConfiguration['data'] {
    const slice = items.slice(0, 8);
    return {
      labels: slice.map((i) => (i.label.length > 28 ? i.label.slice(0, 26) + '…' : i.label)),
      datasets: [
        {
          label: 'Vacantes',
          data: slice.map((i) => i.count),
          backgroundColor: colors(slice.length).map((c) => c + 'cc'),
          borderColor: colors(slice.length),
          borderWidth: 1,
          borderRadius: 4,
          maxBarThickness: 22,
        },
      ],
    };
  }

  private buildVBar(
    items: MarketDistributionItem[],
    _label: string,
  ): ChartConfiguration['data'] {
    return {
      labels: items.map((i) => i.label),
      datasets: [
        {
          label: 'Vacantes',
          data: items.map((i) => i.count),
          backgroundColor: '#941410',
          borderRadius: 6,
          maxBarThickness: 40,
        },
      ],
    };
  }
}
