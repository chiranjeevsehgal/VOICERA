import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClientModule } from '@angular/common/http';
import {
  AudioService,
  Podcast,
} from '../../../services/admin/audio-management.service';
import { HotToastService } from '@ngxpert/hot-toast';
import { Subject } from 'rxjs';
import { debounceTime, distinctUntilChanged } from 'rxjs/operators';

@Component({
  selector: 'app-audio-management',
  standalone: true,
  imports: [CommonModule, FormsModule, HttpClientModule],
  providers: [AudioService],
  templateUrl: './audio-management.component.html',
  styles: ``,
})
export class AudioManagementComponent implements OnInit, OnDestroy {
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
  showEditModal: boolean = false;
  podcastToEdit: Podcast | null = null;
  updating: boolean = false;
  editForm = {
    title: '',
  };

  // Pagination
  totalCount: number = 0;
  currentPage: number = 1;
  limit: number = 20;
  totalPages: number = 0;
  private searchSubject = new Subject<string>();
  private authorSubject = new Subject<string>();

  // Audio player state
  currentlyPlaying: string | null = null;
  audioElement: HTMLAudioElement | null = null;

  constructor(
    private audioService: AudioService,
    private toast: HotToastService
  ) {
    // Debounced search
    this.searchSubject
      .pipe(
        debounceTime(500), // Waiting 500ms after user stops typing
        distinctUntilChanged() // Only emit if value actually changed
      )
      .subscribe(() => {
        this.currentPage = 1;
        this.loadPodcasts();
      });

    // Setup debounced author filter
    this.authorSubject
      .pipe(debounceTime(500), distinctUntilChanged())
      .subscribe(() => {
        this.currentPage = 1;
        this.loadPodcasts();
      });
  }

  ngOnInit() {
    this.loadPodcasts();
  }

  ngOnDestroy() {
    if (this.audioElement) {
      this.audioElement.pause();
    }
    // Complete the subjects to prevent memory leaks
    this.searchSubject.complete();
    this.authorSubject.complete();
  }

  onSearchInput() {
    this.searchSubject.next(this.searchQuery);
  }

  onAuthorInput() {
    this.authorSubject.next(this.selectedAuthor);
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

  // filterPodcasts() {
  //   this.currentPage = 1;
  //   this.loadPodcasts();
  // }

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
        this.podcasts = this.podcasts.filter(
          (p) => p.id !== this.podcastToDelete!.id
        );
        this.filteredPodcasts = this.filteredPodcasts.filter(
          (p) => p.id !== this.podcastToDelete!.id
        );

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

        // Build success message from backend response
        const detailMsg = response?.detail
          ? response.detail
          : `Audio "${this.podcastToDelete!.title}" deleted successfully`;
        const summary = response?.deletion_summary;
        let summaryMsg = '';
        if (summary) {
          const parts: string[] = [];
          if (typeof summary.transcripts_deleted === 'number') {
            parts.push(`Transcripts: ${summary.transcripts_deleted}`);
          }
          if (typeof summary.uploads_deleted === 'number') {
            parts.push(`Uploads: ${summary.uploads_deleted}`);
          }
          if (typeof summary.transcription_stats_deleted === 'number') {
            parts.push(`Transcription stats: ${summary.transcription_stats_deleted}`);
          }
          if (typeof summary.pinecone_vectors_deleted === 'number') {
            parts.push(`Pinecone vectors: ${summary.pinecone_vectors_deleted}`);
          }
          if (Array.isArray(summary.supabase_files_deleted) && summary.supabase_files_deleted.length > 0) {
            parts.push(`Supabase files: ${summary.supabase_files_deleted.length}`);
          }
          if (parts.length) {
            summaryMsg = `\n(${parts.join(' • ')})`;
          }
        }
        this.toast.success(`${detailMsg}${summaryMsg}`);
        this.closeDeleteModal();

        // If current page is empty and not the first page, go to previous page
        if (this.filteredPodcasts.length === 0 && this.currentPage > 1) {
          this.currentPage--;
          this.loadPodcasts();
        }
      },
      error: (error) => {
        console.error('Error deleting audio:', error);
        const backendDetail = error?.error?.detail;
        if (error?.status === 404 && backendDetail) {
          this.toast.error(backendDetail);
        } else if (backendDetail) {
          this.toast.error(backendDetail);
        } else {
          this.toast.error('Failed to delete audio. Please try again.');
        }
        this.deleting = false;
      },
    });
  }

  openEditModal(podcast: Podcast) {
    this.podcastToEdit = podcast;
    this.editForm = {
      title: podcast.title,
    };
    this.showEditModal = true;
  }

  closeEditModal() {
    this.showEditModal = false;
    this.podcastToEdit = null;
    this.updating = false;
    this.editForm = {
      title: '',
    };
  }

  isFormValid(): boolean {
    return (
      this.editForm.title.trim().length > 0
    );
  }

  confirmUpdate() {
    if (!this.podcastToEdit || !this.isFormValid()) return;

    this.updating = true;

    const updateData = {
      title: this.editForm.title.trim(),
    };

    this.audioService.updateAudio(this.podcastToEdit.id, updateData).subscribe({
      next: (updatedPodcast) => {
        // Update the podcast in local arrays
        const podcastIndex = this.podcasts.findIndex(
          (p) => p.id === this.podcastToEdit!.id
        );
        if (podcastIndex !== -1) {
          this.podcasts[podcastIndex] = {
            ...this.podcasts[podcastIndex],
            ...updatedPodcast,
          };
        }

        const filteredIndex = this.filteredPodcasts.findIndex(
          (p) => p.id === this.podcastToEdit!.id
        );
        if (filteredIndex !== -1) {
          this.filteredPodcasts[filteredIndex] = {
            ...this.filteredPodcasts[filteredIndex],
            ...updatedPodcast,
          };
        }

        this.toast.success(
          `Audio "${updatedPodcast.title}" updated successfully`
        );
        this.closeEditModal();
      },
      error: (error) => {
        console.error('Error updating audio:', error);
        this.toast.error('Failed to update audio. Please try again.');
        this.updating = false;
      },
    });
  }
}
