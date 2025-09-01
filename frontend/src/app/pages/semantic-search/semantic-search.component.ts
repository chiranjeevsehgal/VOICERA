import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Subscription } from 'rxjs';
import { HeaderComponent } from '../../components/header/header.component';
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
  imports: [Toast, CommonModule, FormsModule, HeaderComponent],
  providers: [MessageService],
  templateUrl: './semantic-search.component.html',
  styles: ``
})
export class SemanticSearchComponent implements OnInit, OnDestroy {
  searchQuery: string = '';
  searchResults: SemanticPodcast[] = [];
  loading = false;
  hasSearched = false;
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
    this.hasSearched = false;
  }

  private performSearch(query: string): void {
    this.loading = true;
    this.hasSearched = false;
    
    this.subscription = this.semanticSearchService.searchAudio(query).subscribe({
      next: (response) => {
        this.searchResults = this.transformSearchResults(response.results);
        console.log(this.searchResults);
        
        this.loading = false;
        this.hasSearched = true;
      },
      error: (error) => {
        console.error('Search error:', error);
        this.loading = false;
        this.hasSearched = true;
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
      imageUrl: 'https://media.istockphoto.com/id/1244097573/vector/headphones-minimal-icon-with-sound-waves.jpg?s=612x612&w=0&k=20&c=OvARZEMYt_CM9M9-oJmMZ3O-HtEB-CAKqpGZPSA1acM=',
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