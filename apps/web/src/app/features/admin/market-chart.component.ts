import { isPlatformBrowser } from '@angular/common';
import {
  AfterViewInit,
  Component,
  ElementRef,
  Inject,
  Input,
  OnChanges,
  OnDestroy,
  PLATFORM_ID,
  SimpleChanges,
  ViewChild,
} from '@angular/core';
import {
  ArcElement,
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  ChartConfiguration,
  ChartType,
  DoughnutController,
  Legend,
  LinearScale,
  Tooltip,
} from 'chart.js';

Chart.register(
  BarController,
  BarElement,
  CategoryScale,
  LinearScale,
  DoughnutController,
  ArcElement,
  Tooltip,
  Legend,
);

/** Options flexibles: Chart.js tipa bar ≠ doughnut y rompe el template Angular. */
export type MarketChartOptions = Record<string, unknown>;

@Component({
  selector: 'app-market-chart',
  standalone: true,
  template: `
    <div class="mchart" [style.min-height.px]="height">
      <canvas #canvas></canvas>
    </div>
  `,
  styles: [
    `
      .mchart {
        position: relative;
        width: 100%;
      }
      canvas {
        max-width: 100%;
      }
    `,
  ],
})
export class MarketChartComponent implements AfterViewInit, OnChanges, OnDestroy {
  @ViewChild('canvas', { static: true }) canvas!: ElementRef<HTMLCanvasElement>;

  @Input({ required: true }) type!: ChartType;
  @Input({ required: true }) config!: ChartConfiguration['data'];
  @Input() options: MarketChartOptions = {};
  @Input() height = 280;

  private chart: Chart | null = null;
  private ready = false;

  constructor(@Inject(PLATFORM_ID) private readonly platformId: object) {}

  ngAfterViewInit(): void {
    this.ready = true;
    this.render();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (!this.ready) return;
    if (changes['config'] || changes['type'] || changes['options']) {
      this.render();
    }
  }

  ngOnDestroy(): void {
    this.chart?.destroy();
    this.chart = null;
  }

  private render(): void {
    if (!isPlatformBrowser(this.platformId) || !this.canvas || !this.config) return;
    this.chart?.destroy();
    const options = {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 650 },
      ...this.options,
    } as ChartConfiguration['options'];
    this.chart = new Chart(this.canvas.nativeElement, {
      type: this.type,
      data: this.config,
      options,
    });
  }
}
