import { Component } from '@angular/core';
import { PodcastService } from '../../services/podcast.service';

@Component({
  selector: 'app-search',
  standalone: false,
  templateUrl: './search.component.html',
  styles: ``
})
export class SearchComponent {
  podcasts: any[] = []

  constructor(private podcastService: PodcastService) {
    this.podcasts = this.podcastService.getPodcasts()
  }

}
