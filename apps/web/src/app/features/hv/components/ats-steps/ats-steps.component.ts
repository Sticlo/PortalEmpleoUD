import { Component, input, output } from '@angular/core';

@Component({
  selector: 'app-ats-steps',
  templateUrl: './ats-steps.component.html',
})
export class AtsStepsComponent {
  readonly step = input.required<number>();
  readonly labels = input<string[]>(['Tú', 'Estudios', 'Experiencia', 'Proyectos', 'Skills']);
  readonly stepChange = output<number>();
}
