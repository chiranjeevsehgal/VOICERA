import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClientModule } from '@angular/common/http';
import {
  AudioService,
  Podcast,
} from '../../../services/admin/audio-management.service';
import { HotToastService } from '@ngxpert/hot-toast';

@Component({
  selector: 'app-audio-management',
  standalone: true,
  imports: [CommonModule, FormsModule, HttpClientModule],
  providers: [AudioService],
  templateUrl: './audio-management.component.html',
  styles: ``,
})
export class AudioManagementComponent implements OnInit {
  podcasts: Podcast[] = [];
  filteredPodcasts: Podcast[] = [];
  searchQuery: string = '';
  selectedAuthor: string = '';
  loading: boolean = false;
  refreshing: boolean = false;
  error: string = '';
  showDeleteModal: boolean = false;
  podcastToDelete: Podcast | null = null;
  deleting: boolean = false;

  // Pagination
  totalCount: number = 0;
  currentPage: number = 1;
  limit: number = 20;
  totalPages: number = 0;

  // Audio player state
  currentlyPlaying: string | null = null;
  audioElement: HTMLAudioElement | null = null;

  constructor(
    private audioService: AudioService,
    private toast: HotToastService
  ) {}

  ngOnInit() {
    this.loadPodcasts();
  }

  loadPodcasts() {
    if (!this.refreshing) {
      // Only set loading if not refreshing
      this.loading = this.currentPage === 1;
    }
    this.error = '';

    const filters = {
      title_search: this.searchQuery || undefined,
      author: this.selectedAuthor || undefined,
    };

    this.audioService
      .getAudios(this.currentPage, this.limit, filters)
      .subscribe({
        next: (response) => {
          this.totalCount = response.total_count;
          this.totalPages = Math.ceil(this.totalCount / this.limit);
          this.podcasts = response.podcasts;
          this.filteredPodcasts = [...this.podcasts];
          this.loading = false;
          this.refreshing = false;
        },
        error: (error) => {
          console.error('Error loading podcasts:', error);
          this.error = 'Failed to load podcasts. Please try again.';
          this.loading = false;
          this.refreshing = false;
          this.toast.error('Failed to load podcasts. Please try again.');
          this.podcasts = [];
          this.filteredPodcasts = [];
        },
      });
  }

  filterPodcasts() {
    this.currentPage = 1;
    this.loadPodcasts();
  }

  goToPage(page: number) {
    if (page >= 1 && page <= this.totalPages && page !== this.currentPage) {
      this.currentPage = page;
      this.loadPodcasts();
    }
  }

  previousPage() {
    if (this.currentPage > 1) {
      this.goToPage(this.currentPage - 1);
    }
  }

  nextPage() {
    if (this.currentPage < this.totalPages) {
      this.goToPage(this.currentPage + 1);
    }
  }

  getPageNumbers(): number[] {
    const pages: number[] = [];
    const maxVisiblePages = 5;
    let startPage = Math.max(
      1,
      this.currentPage - Math.floor(maxVisiblePages / 2)
    );
    let endPage = Math.min(this.totalPages, startPage + maxVisiblePages - 1);

    if (endPage - startPage + 1 < maxVisiblePages) {
      startPage = Math.max(1, endPage - maxVisiblePages + 1);
    }

    for (let i = startPage; i <= endPage; i++) {
      pages.push(i);
    }

    return pages;
  }

  getMinValue(a: number, b: number): number {
    return Math.min(a, b);
  }

  formatDuration(seconds: number): string {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  }

  formatPublishedDate(date: string): string {
    return new Date(date).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  }

  refreshPodcasts() {
    this.refreshing = true;
    this.currentPage = 1;
    this.loadPodcasts();
  }

  trackPodcastById(index: number, podcast: Podcast): string {
    return podcast.id;
  }

  togglePlayPause(podcast: Podcast) {
    if (this.currentlyPlaying === podcast.id) {
      if (this.audioElement) {
        this.audioElement.pause();
        this.currentlyPlaying = null;
      }
    } else {
      if (this.audioElement) {
        this.audioElement.pause();
      }

      this.audioElement = new Audio(podcast.audio_url);
      this.audioElement
        .play()
        .then(() => {
          this.currentlyPlaying = podcast.id;
        })
        .catch((error) => {
          console.error('Error playing audio:', error);
          this.toast.error('Failed to play audio');
        });

      this.audioElement.onended = () => {
        this.currentlyPlaying = null;
      };
    }
  }

  ngOnDestroy() {
    if (this.audioElement) {
      this.audioElement.pause();
    }
  }

  openDeleteModal(podcast: Podcast) {
    this.podcastToDelete = podcast;
    this.showDeleteModal = true;
  }

  closeDeleteModal() {
    this.showDeleteModal = false;
    this.podcastToDelete = null;
    this.deleting = false;
  }

  confirmDelete() {
    if (!this.podcastToDelete) return;

    this.deleting = true;

    this.audioService.deleteAudio(this.podcastToDelete.id).subscribe({
      next: (response) => {
        // Remove the deleted podcast from local arrays
        this.podcasts = this.podcasts.filter(p => p.id !== this.podcastToDelete!.id);
        this.filteredPodcasts = this.filteredPodcasts.filter(p => p.id !== this.podcastToDelete!.id);
        
        // Update total count
        this.totalCount--;
        this.totalPages = Math.ceil(this.totalCount / this.limit);
        
        // Stop playing if this was the currently playing audio
        if (this.currentlyPlaying === this.podcastToDelete!.id) {
          if (this.audioElement) {
            this.audioElement.pause();
          }
          this.currentlyPlaying = null;
        }

        this.toast.success(`Audio "${this.podcastToDelete!.title}" deleted successfully`);
        this.closeDeleteModal();

        // If current page is empty and not the first page, go to previous page
        if (this.filteredPodcasts.length === 0 && this.currentPage > 1) {
          this.currentPage--;
          this.loadPodcasts();
        }
      },
      error: (error) => {
        console.error('Error deleting audio:', error);
        this.toast.error('Failed to delete audio. Please try again.');
        this.deleting = false;
      }
    });
  }

}