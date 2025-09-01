import { Component, OnInit, OnDestroy } from '@angular/core';
import { Subscription } from 'rxjs';
import { Podcast, PodcastService } from '../../services/podcast.service';
import { HeaderComponent } from '../../components/header/header.component';
import { SerachSectionComponent } from '../../components/search-section/search-section.component';
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
  hasSearched = false;

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
    this.isLoading = true;
    this.subscription = this.podcastService.getPodcasts().subscribe({
      next: (podcasts) => {
        this.podcasts = this.sortPodcastsByDate(podcasts);
        this.filteredPodcasts = podcasts;
        this.isLoading = false
      },
      error: (error) => {
        console.error('Error loading podcasts:', error);
        this.messageService.add({
          severity: 'error',
          summary: 'Error',
          detail: 'Failed to load podcasts',
        });
        this.isLoading = false;
      },
    });
  }

  onSearchChange(query: string): void {
    this.searchQuery = query.trim();
    if (!this.searchQuery) {
      this.hasSearched = false;
    }
    this.filterPodcasts();
  }

  onSearchSubmit(query: string): void {
    this.searchQuery = (query || '').trim();
    this.hasSearched = true;
    this.filterPodcasts();
  }

  private sortPodcastsByDate(podcasts: Podcast[]): Podcast[] {
    return podcasts.sort((a, b) => {
      // Assuming the podcast object has a date field like 'created_at', 'uploadDate', or 'audioFile.created_at'
      // Adjust the property path based on your actual data structure
      const dateA = new Date(
        a.audioFile?.created_at
      );
      const dateB = new Date(
        b.audioFile?.created_at
      );

      // Sort in descending order (newest first)
      return dateB.getTime() - dateA.getTime();
    });
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
