import { Component, OnInit, OnDestroy } from '@angular/core';
import { Subscription } from 'rxjs';
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
export class SearchComponent implements OnInit, OnDestroy {
  podcasts: any[] = [];
  private subscription?: Subscription;

  constructor(
    private podcastService: PodcastService,
    private messageService: MessageService
  ) {}

  ngOnInit(): void {
    this.loadPodcasts();
  }

  ngOnDestroy(): void {
    // Clean up subscription to prevent memory leaks
    if (this.subscription) {
      this.subscription.unsubscribe();
    }
  }

  private loadPodcasts(): void {
    this.subscription = this.podcastService.getPodcasts().subscribe({
      next: (podcasts) => {
        this.podcasts = podcasts;
      },
      error: (error) => {
        console.error('Error loading podcasts:', error);
        this.messageService.add({
          severity: 'error',
          summary: 'Error',
          detail: 'Failed to load podcasts'
        });
      }
    });
  }
}