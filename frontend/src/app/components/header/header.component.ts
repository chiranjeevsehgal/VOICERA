import { Component } from '@angular/core';
import { Router } from '@angular/router';

@Component({
  selector: 'app-header',
  templateUrl: './header.component.html',
  styles: ``,
})
export class HeaderComponent {
  constructor(private router: Router) {}

  onAISearchClick(): void {
    this.router.navigate(['/ai-search']);
  }
  
  onLibraryClick(): void {
    this.router.navigate(['/search']);
  }
}
