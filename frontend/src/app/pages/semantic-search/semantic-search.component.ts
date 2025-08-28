import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Subscription } from 'rxjs';
import { HeaderComponent } from '../../components/header/header.component';
import { AudioModalComponent } from '../../components/audio-modal/audio-modal.component';
import { MessageService } from 'primeng/api';
import { FormsModule } from '@angular/forms';
import { Toast } from 'primeng/toast';
import { SemanticSearchService, SearchResult } from '../../services/semantic-search.service';

export interface SemanticPodcast {
  id: string;
  title: string;
  creator: string;
  imageUrl: string;
  file_url: string;
  searchResult: SearchResult;
}

@Component({
  selector: 'app-semantic-search',
  imports: [Toast, CommonModule, FormsModule, HeaderComponent, AudioModalComponent],
  providers: [MessageService],
  templateUrl: './semantic-search.component.html',
  styles: ``
})
export class SemanticSearchComponent implements OnInit, OnDestroy {
  searchQuery: string = '';
  searchResults: SemanticPodcast[] = [];
  loading = false;
  selectedPodcast: SemanticPodcast | null = null;
  isModalVisible = false;
  private subscription?: Subscription;

  constructor(
    private semanticSearchService: SemanticSearchService,
    private messageService: MessageService
  ) {}

  ngOnInit(): void {}

  ngOnDestroy(): void {
    if (this.subscription) {
      this.subscription.unsubscribe();
    }
  }

  onSearchInput(): void {
    // Optional: Add debouncing here if you want real-time search
  }

  onSearchSubmit(): void {
    if (this.searchQuery.trim()) {
      this.performSearch(this.searchQuery.trim());
    }
  }

  onSearchClear(): void {
    this.searchQuery = '';
    this.searchResults = [];
  }

  private performSearch(query: string): void {
    this.loading = true;
    
    this.subscription = this.semanticSearchService.searchAudio(query).subscribe({
      next: (response) => {
        this.searchResults = this.transformSearchResults(response.results);
        this.loading = false;
      },
      error: (error) => {
        console.error('Search error:', error);
        this.loading = false;
        this.messageService.add({
          severity: 'error',
          summary: 'Search Error',
          detail: 'Failed to perform search. Please try again.'
        });
      }
    });
  }

  private transformSearchResults(results: SearchResult[]): SemanticPodcast[] {
    return results.map((result, index) => ({
      id: `semantic-${index}`,
      title: this.extractTitleFromFilename(result.file_name),
      creator: 'AI Search Result',
      imageUrl: 'https://developers.elementor.com/docs/assets/img/elementor-placeholder-image.png',
      file_url: result.file_url,
      searchResult: result
    }));
  }

  private extractTitleFromFilename(filename: string): string {
    return filename.replace('.mp3', '').replace(/[-_]/g, ' ');
  }

  onPodcastCardClick(podcast: SemanticPodcast): void {
    this.selectedPodcast = podcast;
    this.isModalVisible = true;
  }

  onModalClose(): void {
    this.isModalVisible = false;
    this.selectedPodcast = null;
  }

  formatTime(seconds: number): string {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  }
}