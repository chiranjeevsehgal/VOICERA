import { Component } from '@angular/core';
import { HttpEventType } from '@angular/common/http';
import {
  UploadAudioService,
  UploadResponse,
} from '../../services/upload-audio.service';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HeaderComponent } from '../../components/header/header.component';
import { Router } from '@angular/router';
import { ProfileService } from '../../services/auth/profile.service';
import { HotToastService } from '@ngxpert/hot-toast';

@Component({
  selector: 'app-upload',
  imports: [CommonModule, FormsModule, HeaderComponent],
  providers: [],
  templateUrl: './upload.component.html',
  styles: '',
})
export class UploadComponent {
  selectedFile: File | null = null;
  isDragOver = false;
  isUploading = false;
  uploadProgress = 0;
  uploadStatus = '';
  uploadSuccess = false;
  uploadError = false;
  uploadResponse: UploadResponse | null = null;

  supportedFormats = ['MP3', 'WAV'];

  constructor(
    private uploadService: UploadAudioService,
    private router: Router,
    private profileService: ProfileService,
    private toast: HotToastService
  ) {}

  onDragOver(event: DragEvent) {
    event.preventDefault();
    this.isDragOver = true;
  }

  onDragLeave(event: DragEvent) {
    event.preventDefault();
    this.isDragOver = false;
  }

  onDrop(event: DragEvent) {
    event.preventDefault();
    this.isDragOver = false;

    const files = event.dataTransfer?.files;
    if (files && files.length > 0) {
      this.handleFile(files[0]);
    }
  }

  onFileSelected(event: any) {
    const file = event.target.files[0];
    if (file) {
      this.handleFile(file);
    }
    // Reset the input value so selecting the same file again will trigger change
    if (event?.target) {
      try {
        event.target.value = '';
      } catch {
        // ignore
      }
    }
  }

  private handleFile(file: File) {
    // Allow only MP3 and WAV by extension
    const allowedExtensions = ['mp3', 'wav'];
    const ext = file.name.split('.').pop()?.toLowerCase();
    if (!ext || !allowedExtensions.includes(ext)) {
      this.toast.error('Only MP3 and WAV files are allowed');
      return;
    }

    const maxSize = 50 * 1024 * 1024; // 50MB in bytes
    if (file.size > maxSize) {
      this.toast.error('File size exceeds 50MB limit');
      return;
    }

    this.selectedFile = file;
    this.resetUploadState();
  }

  uploadFile() {
    if (!this.selectedFile) return;

    this.isUploading = true;
    this.uploadProgress = 0;
    this.uploadStatus = 'Preparing upload...';

    this.uploadService.processAudio(this.selectedFile).subscribe({
      next: (event: any) => {
        if (event.type === HttpEventType.UploadProgress) {
          if (event.total) {
            this.uploadProgress = Math.round(
              (100 * event.loaded) / event.total,
            );
            this.updateUploadStatus();
          }
        } else if (event.type === HttpEventType.Response) {
          this.uploadProgress = 100;
          this.uploadStatus = 'Upload complete!';
          this.uploadResponse = event.body;
          this.profileService.refreshCredits();
          setTimeout(() => {
            this.isUploading = false;
            this.uploadSuccess = true;
          }, 500);
        }
      },
      error: (error) => {
        this.isUploading = false;
        console.error('Upload failed. Please try again.');
      },
    });
  }

  private updateUploadStatus() {
    if (this.uploadProgress < 30) {
      this.uploadStatus = 'Uploading audio file...';
    } else if (this.uploadProgress < 70) {
      this.uploadStatus = 'Validating file...';
    } else if (this.uploadProgress < 100) {
      this.uploadStatus = 'Processing request...';
    }
  }

  trackJob() {
    if (this.uploadResponse?.job_id) {
      this.router.navigate(['/track'], {
        queryParams: { jobId: this.uploadResponse.job_id },
      });
    }
  }

  clearFile() {
    this.selectedFile = null;
    this.resetUploadState();
  }

  uploadAnother() {
    this.selectedFile = null;
    this.uploadResponse = null;
    this.resetUploadState();
  }

  retryUpload() {
    this.resetUploadState();
  }

  private resetUploadState() {
    this.isUploading = false;
    this.uploadProgress = 0;
    this.uploadStatus = '';
    this.uploadSuccess = false;
    this.uploadError = false;
  }

  formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  getFileType(filename: string): string {
    const extension = filename.split('.').pop()?.toLowerCase();
    return extension ? extension.toUpperCase() : 'Unknown';
  }

  navigateToTrack() {
    this.router.navigate(['/track']);
  }
}
