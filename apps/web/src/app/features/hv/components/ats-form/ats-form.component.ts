import { Component, inject, input, output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { parseSkillTokens } from '../../../../core/hv-ats-export';
import { HvProfileService } from '../../../../core/hv-profile.service';

@Component({
  selector: 'app-ats-form',
  imports: [FormsModule],
  templateUrl: './ats-form.component.html',
})
export class AtsFormComponent {
  readonly step = input.required<number>();
  readonly totalSteps = input(5);
  readonly saving = input(false);
  readonly next = output<void>();
  readonly prev = output<void>();
  readonly save = output<void>();
  readonly download = output<void>();

  readonly hv = inject(HvProfileService);
  skillDraft = '';
  langDraft = '';

  addSkill(): void {
    const tokens = parseSkillTokens(this.skillDraft);
    if (!tokens.length) return;
    const current = [...this.hv.profile().skills];
    for (const s of tokens) {
      if (!current.some((x) => x.toLowerCase() === s.toLowerCase())) {
        current.push(s);
      }
    }
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

  addLanguage(): void {
    const tokens = parseSkillTokens(this.langDraft);
    if (!tokens.length) return;
    const current = [...this.hv.profile().languages];
    for (const s of tokens) {
      if (!current.some((x) => x.toLowerCase() === s.toLowerCase())) {
        current.push(s);
      }
    }
    this.hv.setLanguages(current);
    this.langDraft = '';
  }

  removeLanguage(index: number): void {
    const current = [...this.hv.profile().languages];
    current.splice(index, 1);
    this.hv.setLanguages(current);
  }

  onLangKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter') {
      event.preventDefault();
      this.addLanguage();
    }
  }

  onSubmit(event: Event): void {
    event.preventDefault();
    this.save.emit();
  }
}
