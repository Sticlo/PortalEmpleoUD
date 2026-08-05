import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

@Component({
  selector: 'app-main-nav',
  imports: [RouterLink, RouterLinkActive],
  templateUrl: './main-nav.component.html',
  styleUrl: './main-nav.component.css',
})
export class MainNavComponent {}
