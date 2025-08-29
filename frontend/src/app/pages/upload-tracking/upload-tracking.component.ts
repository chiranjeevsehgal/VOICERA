import { Component, OnDestroy, OnInit } from '@angular/core';
import { interval, Subscription } from 'rxjs';
import { ActivatedRoute } from '@angular/router';
import { UploadAudioService, JobStatus } from '../../services/upload-audio.service';
import { MessageService } from 'primeng/api';
import { CommonModule } from '@angular/common';
import { Toast } from 'primeng/toast';
import { HeaderComponent } from '../../components/header/header.component';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-upload-tracking',
  imports: [Toast, CommonModule, FormsModule, HeaderComponent],
  providers: [MessageService],
  templateUrl: './upload-tracking.component.html',
  styles: ``
})
export class UploadTrackingComponent implements OnInit, OnDestroy {
  jobId = '';
  jobStatus: JobStatus | null = null;
  loading = false;
  autoRefresh = false;
  refreshSubscription?: Subscription;
  errorMessage = '';

  private readonly processingStatuses = [
    'pending',
    'checking_credits',
    'uploading',
    'transcribing',
    'embedding',
    'indexing',
    'uploading_to_supabase',
    'deducting_credits'
  ];

  constructor(
    private route: ActivatedRoute,
    private uploadService: UploadAudioService
  ) {}

  ngOnInit() {
    this.route.queryParams.subscribe(params => {
      if (params['jobId']) {
        this.jobId = params['jobId'];
        this.checkStatus();
      }
    });
  }

  ngOnDestroy() {
    if (this.refreshSubscription) {
      this.refreshSubscription.unsubscribe();
    }
  }

  checkStatus() {
    if (!this.jobId.trim()) return;

    this.loading = true;
    this.errorMessage = '';
    
    this.uploadService.getJobStatus(this.jobId).subscribe({
      next: (status) => {
        this.jobStatus = status;
        this.loading = false;
        
        // Auto-enable refresh for processing jobs
        if (this.isProcessingStatus() && !this.autoRefresh) {
          this.autoRefresh = true;
          this.startAutoRefresh();
        } else if (status.status === 'completed' || status.status === 'failed') {
          this.autoRefresh = false;
          this.stopAutoRefresh();
        }
      },
      error: (error:any) => {
        this.loading = false;
        this.errorMessage = error.error?.message || 'Failed to fetch job status. Please check your job ID and try again.';
      }
    });
  }

  isProcessingStatus(): boolean {
    return this.jobStatus ? this.processingStatuses.includes(this.jobStatus.status) : false;
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
    this.refreshSubscription = interval(5000).subscribe(() => {
      if (this.jobStatus && this.isProcessingStatus()) {
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
      case 'checking_credits':
        return 'Checking Credits';
      case 'uploading':
        return 'Uploading File';
      case 'transcribing':
        return 'Transcribing Audio';
      case 'embedding':
        return 'Creating Embeddings';
      case 'indexing':
        return 'Indexing Content';
      case 'uploading_to_supabase':
        return 'Storing Data';
      case 'deducting_credits':
        return 'Processing Payment';
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
      case 'checking_credits':
        return 'Verifying your account credits and permissions';
      case 'uploading':
        return 'Uploading your audio file to our servers';
      case 'transcribing':
        return 'Converting audio speech to text using AI';
      case 'embedding':
        return 'Generating semantic embeddings for search';
      case 'indexing':
        return 'Indexing content for fast retrieval';
      case 'uploading_to_supabase':
        return 'Storing processed data in the database';
      case 'deducting_credits':
        return 'Finalizing billing and credit deduction';
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
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  }

  formatDate(dateString: string): string {
    const date = new Date(dateString);
    return date.toLocaleString();
  }
}
