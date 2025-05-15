import { Component, Input } from '@angular/core';

@Component({
  selector: 'app-podcast-grid',
  standalone: false,
  templateUrl: './podcast-grid.component.html',
  styles: ``
})
export class PodcastGridComponent {
  @Input() podcasts: any[] = [];
}
