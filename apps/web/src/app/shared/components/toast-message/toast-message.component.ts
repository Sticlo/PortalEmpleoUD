import { Component, inject } from '@angular/core';
import { ToastService } from '../../../core/toast.service';

@Component({
  selector: 'app-toast-message',
  template: `
    @if (toast.message(); as msg) {
      <div class="toast">{{ msg }}</div>
    }
  `,
})
export class ToastMessageComponent {
  readonly toast = inject(ToastService);
}
