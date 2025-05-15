import { Component, Input } from '@angular/core';

@Component({
  selector: 'app-podcast-card',
  standalone: false,
  templateUrl: './podcast-card.component.html',
  styles: ``
})
export class PodcastCardComponent {
  @Input() podcast!: any;
}
