import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClientModule } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { LogsService, LogFile, LogFilesResponse } from '../../../services/admin/logs.service';

@Component({
  selector: 'app-application-logs',
  standalone: true,
  imports: [CommonModule, HttpClientModule, FormsModule],
  providers: [LogsService],
  templateUrl: './application-logs.component.html',
  styles: ``
})
export class ApplicationLogsComponent implements OnInit {
  loading = false;
  refreshing = false;
  error = '';
  
  logFiles: LogFile[] = [];
  totalFiles = 0;
  
  // Search functionality
  searchTerm = '';
  filteredLogFiles: LogFile[] = [];

  constructor(
    private logsService: LogsService,
    private router: Router
  ) {}

  ngOnInit(): void {
    this.loadLogFiles();
  }

  loadLogFiles(): void {
    this.loading = true;
    this.error = '';
    
    this.logsService.getLogFiles().subscribe({
      next: (response: LogFilesResponse) => {
        this.logFiles = response.log_files;
        this.totalFiles = response.total_count;
        this.applySearch();
        this.loading = false;
        this.refreshing = false;
      },
      error: (err) => {
        console.error('Failed to load log files', err);
        this.error = 'Failed to load log files. Please try again.';
        this.loading = false;
        this.refreshing = false;
      }
    });
  }

  refresh(): void {
    this.refreshing = true;
    this.loadLogFiles();
  }

  applySearch(): void {
    if (!this.searchTerm.trim()) {
      this.filteredLogFiles = [...this.logFiles];
    } else {
      const term = this.searchTerm.toLowerCase();
      this.filteredLogFiles = this.logFiles.filter(file => 
        file.filename.toLowerCase().includes(term) ||
        file.date.toLowerCase().includes(term)
      );
    }
  }

  onSearchChange(): void {
    this.applySearch();
  }

  clearSearch(): void {
    this.searchTerm = '';
    this.applySearch();
  }

  viewLogFile(filename: string): void {
    this.router.navigate(['/admin/application-logs', filename]);
  }

  formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 B';
    
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  formatDate(dateString: string): string {
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return '—';
    
    return date.toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  }

  getDateBadgeClass(dateString: string): string {
    const date = new Date(dateString);
    const now = new Date();
    const diffHours = (now.getTime() - date.getTime()) / (1000 * 60 * 60);
    
    if (diffHours < 24) return 'bg-green-100 text-green-800';
    if (diffHours < 168) return 'bg-blue-100 text-blue-800'; // 7 days
    return 'bg-gray-100 text-gray-800';
  }

  trackByFilename(index: number, file: LogFile): string {
    return file.filename;
  }

  getTotalSize(): string {
    const totalBytes = this.logFiles.reduce((sum, file) => sum + file.size, 0);
    return this.formatFileSize(totalBytes);
  }
}
