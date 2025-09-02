import { Component, Input, Output, EventEmitter, OnInit, OnDestroy, ElementRef, ViewChild, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Podcast, PodcastService } from '../../services/podcast.service';
import { take } from 'rxjs';

@Component({
  selector: 'app-audio-modal',
  imports: [CommonModule],
  templateUrl: './audio-modal.component.html',
  styles: ``
})
export class AudioModalComponent implements OnInit, OnDestroy, OnChanges {
  @Input() podcast: Podcast | null = null;
  @Input() isVisible = false;
  @Output() close = new EventEmitter<void>();
  @ViewChild('audioPlayer') audioPlayer!: ElementRef<HTMLAudioElement>;

  duration = 0;
  currentTime = 0;
  isPlaying = false;

  // Transcript state
  transcript: string | null = null;
  transcriptLoading = false;
  transcriptError: string | null = null;

  constructor(private podcastService: PodcastService) {}

  ngOnInit() {
    if (this.isVisible) {
      document.body.style.overflow = 'hidden';
    }
  }

  ngOnDestroy() {
    document.body.style.overflow = 'auto';
  }

  ngOnChanges(changes: SimpleChanges): void {
    const becameVisible = changes['isVisible']?.currentValue === true && changes['isVisible']?.previousValue !== true;
    const podcastChanged = !!changes['podcast'];

    if ((becameVisible || podcastChanged) && this.isVisible) {
      this.fetchTranscript();
    }
  }

  onBackdropClick(event: MouseEvent) {
    if (event.target === event.currentTarget) {
      this.closeModal();
    }
  }

  closeModal() {
    this.isVisible = false;
    document.body.style.overflow = 'auto';
    if (this.audioPlayer?.nativeElement) {
      this.audioPlayer.nativeElement.pause();
    }
    this.close.emit();
  }

  onTimeUpdate() {
    if (this.audioPlayer?.nativeElement) {
      this.currentTime = this.audioPlayer.nativeElement.currentTime;
    }
  }

  onLoadedMetadata() {
    if (this.audioPlayer?.nativeElement) {
      console.log(this.audioPlayer.nativeElement);
      
      this.duration = this.audioPlayer.nativeElement.duration;
    }
  }

  private fetchTranscript() {
    // Reset state
    this.transcript = null;
    this.transcriptError = null;

    const mp3Url = this.podcast?.audioFile?.user_data?.file_url;
    if (!mp3Url) return;

    this.transcriptLoading = true;
    this.podcastService
      .extractTranscript(mp3Url)
      .pipe(take(1))
      .subscribe({
        next: (text) => {
          this.transcript = text || '';
          this.transcriptLoading = false;
        },
        error: (err) => {
          this.transcriptError = err?.error?.detail || 'Failed to fetch transcript';
          this.transcriptLoading = false;
        }
      });
  }

  formatTime(seconds: number): string {
    if (!seconds || isNaN(seconds)) return '0:00';
    
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  }

  formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  formatDate(dateString: string): string {
    return new Date(dateString).toLocaleDateString();
  }
}