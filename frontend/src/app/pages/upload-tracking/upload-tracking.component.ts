import { Component, OnDestroy, OnInit } from '@angular/core';
import { interval, Subscription } from 'rxjs';
import { ActivatedRoute } from '@angular/router';
import {
  UploadAudioService,
  JobStatus,
} from '../../services/upload-audio.service';
import { MessageService } from 'primeng/api';
import { CommonModule } from '@angular/common';
import { Toast } from 'primeng/toast';
import { HeaderComponent } from '../../components/header/header.component';
import { FormsModule } from '@angular/forms';
import { ProfileService } from '../../services/auth/profile.service';

@Component({
  selector: 'app-upload-tracking',
  imports: [Toast, CommonModule, FormsModule, HeaderComponent],
  providers: [MessageService],
  templateUrl: './upload-tracking.component.html',
  styles: ``,
})
export class UploadTrackingComponent implements OnInit, OnDestroy {
  jobId = '';
  jobStatus: JobStatus | null = null;
  loading = false;
  autoRefresh = false;
  refreshSubscription?: Subscription;
  errorMessage = '';
  manualRefreshInProgress = false;

  private readonly processingStatuses = [
    'pending',
    'uploading',
    'transcribing',
    'embedding',
    'indexing',
    'uploading_to_supabase',
  ];

  constructor(
    private route: ActivatedRoute,
    private uploadService: UploadAudioService,
    private profileService: ProfileService
  ) {}

  ngOnInit() {
    this.route.queryParams.subscribe((params) => {
      if (params['jobId']) {
        this.jobId = params['jobId'];
        this.checkStatus();
      }
    });
  }

  ngOnDestroy() {
    this.stopAutoRefresh();
  }

  checkStatus() {
    if (!this.jobId.trim()) return;

    // Track if this is a manual refresh to prevent auto-enabling auto-refresh
    this.manualRefreshInProgress = !this.loading;
    this.loading = true;
    this.errorMessage = '';

    this.uploadService.getJobStatus(this.jobId).subscribe({
      next: (status: any) => {
        this.jobStatus = status;
        this.loading = false;

        if (
          this.isProcessingStatus() &&
          !this.autoRefresh &&
          !this.manualRefreshInProgress
        ) {
          this.autoRefresh = true;
          this.startAutoRefresh();
        } else if (
          status.status === 'completed' ||
          status.status === 'failed'
        ) {
          this.autoRefresh = false;
          this.stopAutoRefresh();
        }
        this.profileService.refreshCredits();
        this.manualRefreshInProgress = false;
      },
      error: (error) => {
        this.loading = false;
        this.manualRefreshInProgress = false;
        this.errorMessage =
          error.error?.message ||
          'Failed to fetch job status. Please check your job ID and try again.';
      },
    });
  }

  isProcessingStatus(): boolean {
    return this.jobStatus
      ? this.processingStatuses.includes(this.jobStatus.status)
      : false;
  }

  toggleAutoRefresh() {
    if (this.autoRefresh) {
      this.startAutoRefresh();
    } else {
      this.stopAutoRefresh();
    }
  }

  private startAutoRefresh() {
    this.stopAutoRefresh();
    this.refreshSubscription = interval(10000).subscribe(() => {
      // Changed to 10 seconds
      if (this.jobStatus && this.isProcessingStatus()) {
        // Don't treat auto-refresh as manual refresh
        this.manualRefreshInProgress = false;
        this.checkStatus();
      } else {
        this.autoRefresh = false;
        this.stopAutoRefresh();
      }
    });
  }

  private stopAutoRefresh() {
    if (this.refreshSubscription) {
      this.refreshSubscription.unsubscribe();
      this.refreshSubscription = undefined;
    }
  }

  trackAnother() {
    this.jobId = '';
    this.jobStatus = null;
    this.errorMessage = '';
    this.autoRefresh = false;
    this.manualRefreshInProgress = false;
    this.stopAutoRefresh();
  }

  retryCheck() {
    this.errorMessage = '';
    this.checkStatus();
  }

  getStatusTitle(): string {
    if (!this.jobStatus) return '';

    switch (this.jobStatus.status) {
      case 'pending':
        return 'Job Queued';
      case 'uploading':
        return 'Uploading File';
      case 'transcribing':
        return 'Transcribing Audio';
      case 'embedding':
        return 'Creating Embeddings';
      case 'indexing':
        return 'Indexing Content';
      case 'completed':
        return 'Processing Complete!';
      case 'failed':
        return 'Processing Failed';
      default:
        return 'Processing Audio';
    }
  }

  getStatusDescription(): string {
    if (!this.jobStatus) return '';

    switch (this.jobStatus.status) {
      case 'pending':
        return 'Your job is waiting in the queue to be processed';
      case 'uploading':
        return 'Uploading your audio file to our servers';
      case 'transcribing':
        return 'Converting audio speech to text using AI';
      case 'embedding':
        return 'Generating semantic embeddings for search';
      case 'indexing':
        return 'Indexing content for fast retrieval';
      case 'completed':
        return 'Your audio has been successfully processed and is now searchable';
      case 'failed':
        return 'An error occurred during processing';
      default:
        return 'Processing your audio file';
    }
  }

  getStatusDisplayName(): string {
    if (!this.jobStatus) return '';

    return this.jobStatus.status
      .split('_')
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  }

  formatDate(dateString: string): string {
    const date = new Date(dateString);
    return date.toLocaleString();
  }

  getProgressColor(): string {
  if (!this.jobStatus) return 'bg-gray-300';
  
  const progress = this.jobStatus.progress;
  
  if (progress < 25) {
    return 'bg-gradient-to-r from-red-500 via-orange-500 to-yellow-500';
  } else if (progress < 50) {
    return 'bg-gradient-to-r from-yellow-500 via-yellow-400 to-amber-500';
  } else if (progress < 75) {
    return 'bg-gradient-to-r from-amber-500 via-blue-500 to-cyan-500';
  } else if (progress < 100) {
    return 'bg-gradient-to-r from-cyan-500 via-blue-500 to-indigo-600';
  } else {
    return 'bg-gradient-to-r from-green-500 via-emerald-500 to-green-600';
  }
}
}
