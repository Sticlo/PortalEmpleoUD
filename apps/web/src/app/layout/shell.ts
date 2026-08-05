import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import {
  MainNavComponent,
  SiteFooterComponent,
  SiteHeaderComponent,
  ToastMessageComponent,
  TopbarComponent,
} from '../shared/components';

@Component({
  selector: 'app-shell',
  imports: [
    RouterOutlet,
    TopbarComponent,
    SiteHeaderComponent,
    MainNavComponent,
    SiteFooterComponent,
    ToastMessageComponent,
  ],
  templateUrl: './shell.html',
  styleUrl: './shell.css',
})
export class Shell {}
