import { Component, OnInit, OnDestroy } from '@angular/core';
import { Subscription } from 'rxjs';
import { Podcast, PodcastService } from '../../services/podcast.service';
import { HeaderComponent } from '../../components/header/header.component';
import { SerachSectionComponent } from '../../components/search-section/search-section.component';
import { TrendingSearchesComponent } from '../../components/trending-searches/trending-searches.component';
import { PodcastGridComponent } from '../../components/podcast-grid/podcast-grid.component';
import { MessageService } from 'primeng/api';
import { AudioModalComponent } from '../../components/audio-modal/audio-modal.component';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-search',
  templateUrl: './search.component.html',
  styles: ``,
  imports: [
    CommonModule,
    HeaderComponent,
    SerachSectionComponent,
    TrendingSearchesComponent,
    AudioModalComponent,
    PodcastGridComponent,
  ],
  providers: [MessageService],
})
export class SearchComponent implements OnInit, OnDestroy {
  podcasts: any[] = [];
  filteredPodcasts: Podcast[] = [];
  searchQuery: string = '';
  selectedPodcast: Podcast | null = null;
  isModalVisible = false;
  private subscription?: Subscription;
  isSearching = false;
  isLoading = true;

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
        this.filteredPodcasts = podcasts;
      },
      error: (error) => {
        console.error('Error loading podcasts:', error);
        this.messageService.add({
          severity: 'error',
          summary: 'Error',
          detail: 'Failed to load podcasts',
        });
      },
    });
  }

  onSearchChange(query: string): void {
    this.searchQuery = query.trim();
    this.filterPodcasts();
  }

  private filterPodcasts(): void {
    if (!this.searchQuery) {
      this.filteredPodcasts = this.podcasts;
    } else {
      this.filteredPodcasts = this.podcasts.filter(
        (podcast) =>
          podcast.title
            .toLowerCase()
            .includes(this.searchQuery.toLowerCase()) ||
          podcast.creator.toLowerCase().includes(this.searchQuery.toLowerCase())
      );
    }
  }

  onPodcastCardClick(podcast: Podcast): void {
    this.selectedPodcast = podcast;
    this.isModalVisible = true;
  }

  onModalClose(): void {
    this.isModalVisible = false;
    this.selectedPodcast = null;
  }
}
