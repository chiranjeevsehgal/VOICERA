import { Component, EventEmitter, Input, Output } from '@angular/core';
import { Podcast } from '../../services/podcast.service';

@Component({
  selector: 'app-podcast-card',
  templateUrl: './podcast-card.component.html',
  styles: ``,
})
export class PodcastCardComponent {
  @Input() podcast!: any;
  @Output() cardClick = new EventEmitter<Podcast>();

  onCardClick() {
    this.cardClick.emit(this.podcast);
  }
}
