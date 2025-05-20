import { Component } from '@angular/core';
import { PodcastService } from '../../services/podcast.service';
import { HeaderComponent } from '../../components/header/header.component';
import { SerachSectionComponent } from '../../components/search-section/search-section.component';
import { TrendingSearchesComponent } from '../../components/trending-searches/trending-searches.component';
import { PodcastGridComponent } from '../../components/podcast-grid/podcast-grid.component';
import { MessageService } from 'primeng/api';

@Component({
    selector: 'app-search',
    templateUrl: './search.component.html',
    styles: ``,
    imports: [
      HeaderComponent, 
      SerachSectionComponent, 
      TrendingSearchesComponent, 
      PodcastGridComponent
    ],
    providers : [
      MessageService
    ]
})
export class SearchComponent {
  podcasts: any[] = []

  constructor(
    private podcastService: PodcastService,
    private messageService : MessageService
  ) {
    this.podcasts = this.podcastService.getPodcasts()
  }

}
