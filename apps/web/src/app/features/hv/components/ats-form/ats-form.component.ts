import { Component, inject, input, output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HvProfileService } from '../../../../core/hv-profile.service';

@Component({
  selector: 'app-ats-form',
  imports: [FormsModule],
  templateUrl: './ats-form.component.html',
})
export class AtsFormComponent {
  readonly step = input.required<number>();
  readonly totalSteps = input(4);
  readonly saving = input(false);
  readonly next = output<void>();
  readonly prev = output<void>();
  readonly save = output<void>();

  readonly hv = inject(HvProfileService);
  skillDraft = '';

  addSkill(): void {
    const raw = this.skillDraft.trim();
    if (!raw) return;
    const current = [...this.hv.profile().skills];
    raw.split(',').forEach((part) => {
      const s = part.trim();
      if (s && !current.some((x) => x.toLowerCase() === s.toLowerCase())) {
        current.push(s);
      }
    });
    this.hv.setSkills(current);
    this.skillDraft = '';
  }

  removeSkill(index: number): void {
    const current = [...this.hv.profile().skills];
    current.splice(index, 1);
    this.hv.setSkills(current);
  }

  onSkillKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter') {
      event.preventDefault();
      this.addSkill();
    }
  }

  onSubmit(event: Event): void {
    event.preventDefault();
    this.save.emit();
  }
}
