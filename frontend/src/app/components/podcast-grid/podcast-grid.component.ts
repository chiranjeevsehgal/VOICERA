import { Component, EventEmitter, Input, Output } from '@angular/core';
import { PodcastCardComponent } from '../podcast-card/podcast-card.component';
import { Podcast } from '../../services/podcast.service';

@Component({
  selector: 'app-podcast-grid',
  templateUrl: './podcast-grid.component.html',
  styles: ``,
  imports: [PodcastCardComponent],
})
export class PodcastGridComponent {
  @Input() podcasts: any[] = [];
  @Output() podcastClick = new EventEmitter<Podcast>();

  onCardClick(podcast: Podcast): void {
    this.podcastClick.emit(podcast);
  }
}
