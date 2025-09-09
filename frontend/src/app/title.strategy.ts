import { Injectable } from '@angular/core';
import { Title } from '@angular/platform-browser';
import { RouterStateSnapshot, TitleStrategy } from '@angular/router';

@Injectable({ providedIn: 'root' })
export class AppTitleStrategy extends TitleStrategy {
  constructor(private readonly title: Title) {
    super();
  }

  override updateTitle(snapshot: RouterStateSnapshot): void {
    const currentTitle = this.buildTitle(snapshot);
    if (currentTitle) {
      this.title.setTitle(`Voicera - ${currentTitle}`);
    } else {
      this.title.setTitle('Voicera');
    }
  }
}
