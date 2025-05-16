import { Component, Input } from '@angular/core';
import { PodcastCardComponent } from '../podcast-card/podcast-card.component';

@Component({
    selector: 'app-podcast-grid',
    templateUrl: './podcast-grid.component.html',
    styles: ``,
    imports: [PodcastCardComponent]
})
export class PodcastGridComponent {
  @Input() podcasts: any[] = [];
}
