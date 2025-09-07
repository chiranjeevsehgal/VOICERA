import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Podcast } from '../../services/podcast.service';

@Component({
  selector: 'app-podcast-list',
  templateUrl: './podcast-list.component.html',
  styles: ``,
  imports: [CommonModule],
})
export class PodcastListComponent {
  @Input() podcasts: any[] = [];
  @Output() podcastClick = new EventEmitter<Podcast>();

  onRowClick(podcast: Podcast): void {
    this.podcastClick.emit(podcast);
  }
}
