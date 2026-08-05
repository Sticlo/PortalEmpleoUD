import { Component } from '@angular/core';
import { HomeHeroComponent } from './components/home-hero/home-hero.component';
import { HowItWorksComponent } from './components/how-it-works/how-it-works.component';

@Component({
  selector: 'app-home-page',
  imports: [HomeHeroComponent, HowItWorksComponent],
  templateUrl: './home.page.html',
})
export class HomePage {}
