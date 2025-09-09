import { Component, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClientModule } from '@angular/common/http';
import { BulkUploadService, BulkUploadResponse, JobStatus } from '../../../services/admin/bulk-upload.service';
import {
  shouldUseMockData,
} from '../../../utils/role.utils';
import { HotToastService } from '@ngxpert/hot-toast';

interface UploadFileRow {
  file: File;
  customName: string;
  sizeMB: number;
}

@Component({
  selector: 'app-bulk-upload',
  standalone: true,
  imports: [CommonModule, FormsModule, HttpClientModule],
  templateUrl: './bulk-upload.component.html',
  styles: ``,
})
export class BulkUploadComponent implements OnDestroy {
  // File selection
  files: UploadFileRow[] = [];
  maxFiles = 50;
  maxFileSizeMB = 50;

  // Options and validation
  // Safe defaults for Deepgram: auto-detect language and readable formatting
  transcriptionOptionsText = '{\n  "detect_language": true,\n  "punctuate": true,\n  "smart_format": true,\n  "model": "nova-2"\n}';
  optionsError: string = '';

  // Submission state
  submitting = false;
  lastResponse: BulkUploadResponse | null = null;
  showTrackingModal = false;

  // Tracking jobs
  jobStatuses: { file: string; job_id: string; status?: string; progress?: number; error?: string; }[] = [];
  tracking = false;
  private trackingTimer: any = null;
  pollIntervalMs = 2500;

  constructor(
    private bulkService: BulkUploadService,
    private toast: HotToastService
  ) {}

  ngOnDestroy(): void {
    this.stopTracking();
  }

  onFilesSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (!input.files) return;

    const selected = Array.from(input.files);

    // Enforce max files
    const combined = [...this.files, ...selected.map((f) => ({
      file: f,
      customName: f.name,
      sizeMB: Math.round((f.size / (1024 * 1024)) * 100) / 100,
    }))];

    if (combined.length > this.maxFiles) {
      const allowed = this.maxFiles - this.files.length;
      this.files.push(
        ...selected
          .slice(0, Math.max(0, allowed))
          .map((f) => ({ file: f, customName: f.name, sizeMB: Math.round((f.size / (1024 * 1024)) * 100) / 100 }))
      );
    } else {
      this.files = combined;
    }

    // Remove oversized files
    this.files = this.files.filter((row) => row.sizeMB <= this.maxFileSizeMB);

    // Reset input so same files can be re-selected later
    input.value = '';
  }

  removeFile(index: number): void {
    this.files.splice(index, 1);
  }

  clearFiles(): void {
    this.files = [];
  }

  private parseOptions(): any | null {
    try {
      const parsed = JSON.parse(this.transcriptionOptionsText || '{}');
      if (typeof parsed !== 'object' || Array.isArray(parsed)) {
        this.optionsError = 'Transcription options must be a JSON object';
        return null;
      }
      // Normalize options to avoid Deepgram errors
      // If language is set to an unsupported value like 'auto', switch to detect_language
      if (typeof parsed.language === 'string') {
        const lang = parsed.language.trim().toLowerCase();
        if (!lang || lang === 'auto') {
          delete parsed.language;
          parsed.detect_language = true;
        }
      }
      // Ensure a safe default model if none provided
      if (!parsed.model || typeof parsed.model !== 'string' || !parsed.model.trim()) {
        parsed.model = 'nova-2';
      }
      this.optionsError = '';
      return parsed;
    } catch (e: any) {
      this.optionsError = `Invalid JSON: ${e?.message || e}`;
      return null;
    }
  }

  canSubmit(): boolean {
    return !this.submitting && this.files.length > 0 && !this.optionsError;
  }

  startUpload(): void {
    // Check if we're in mock/guest mode
    if (shouldUseMockData()) {
      this.toast.error(
        'Bulk upload is not allowed in guest mode.',
        {
          duration: 5000,
          position: 'top-center'
        }
      );
      return;
    }

    const options = this.parseOptions();
    if (!options) return;
    if (this.files.length === 0) return;

    this.submitting = true;

    const filenameMap: Record<string, string> = {};
    // Map by original filename (backend supports both index and name keys)
    this.files.forEach((row) => {
      if (row.customName && row.customName !== row.file.name) {
        filenameMap[row.file.name] = row.customName.trim();
      }
    });

    const files = this.files.map((r) => r.file);

    this.bulkService.bulkUpload(files, filenameMap, options).subscribe({
      next: (resp) => {
        this.lastResponse = resp;
        // Prepare job status entries
        this.jobStatuses = (resp.items || []).map((it) => ({ file: it.file, job_id: it.job_id }));
        this.submitting = false;
        this.showTrackingModal = true;
      },
      error: (err) => {
        console.error('Bulk upload error', err);
        this.submitting = false;
        alert(err?.error?.detail?.message || err?.error?.detail || 'Bulk upload failed');
      }
    });
  }

  trackProgress(): void {
    if (shouldUseMockData()) {
      this.toast.info('Progress tracking is disabled in guest mode.');
      return;
    }

    if (this.tracking) return;
    this.tracking = true;
    this.trackingTimer = setInterval(() => {
      this.pollStatusesOnce();
    }, this.pollIntervalMs);
    // immediate poll once
    this.pollStatusesOnce();
  }

  stopTracking(): void {
    if (this.trackingTimer) {
      clearInterval(this.trackingTimer);
      this.trackingTimer = null;
    }
    this.tracking = false;
  }

  private pollStatusesOnce(): void {
    if (!this.jobStatuses || this.jobStatuses.length === 0) return;

    this.jobStatuses.forEach((job, idx) => {
      this.bulkService.getJobStatus(job.job_id).subscribe({
        next: (status: JobStatus) => {
          this.jobStatuses[idx] = {
            ...job,
            status: status.status,
            progress: status.progress,
            error: status.error,
          };
        },
        error: (err) => {
          console.warn('Status error', job.job_id, err);
          this.jobStatuses[idx] = {
            ...job,
            status: 'error',
            error: err?.error?.detail || 'Failed to fetch status',
          };
        }
      });
    });
  }
}