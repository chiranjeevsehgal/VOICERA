import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import {
  LogsService,
  LogFile,
  LogFilesResponse,
} from '../../../services/admin/logs.service';
import { shouldUseMockData } from '../../../utils/role.utils';
import * as mockLogsData from '../../../utils/mockData/mockLogs.json';
import { HotToastService } from '@ngxpert/hot-toast';

@Component({
  selector: 'app-application-logs',
  standalone: true,
  imports: [CommonModule, FormsModule],
  providers: [LogsService],
  templateUrl: './application-logs.component.html',
  styles: ``,
})
export class ApplicationLogsComponent implements OnInit {
  loading = false;
  refreshing = false;

  logFiles: LogFile[] = [];
  totalFiles = 0;

  // Search functionality
  searchTerm = '';
  filteredLogFiles: LogFile[] = [];

  // UI/UX state
  sortBy: 'last_modified' | 'size' | 'filename' | 'date' = 'last_modified';
  sortDir: 'asc' | 'desc' = 'desc';
  density: 'comfortable' | 'compact' = 'comfortable';
  showRecentOnly = false; // last 7 days

  constructor(
    private logsService: LogsService,
    private router: Router,
    private toast: HotToastService,
  ) {}

  ngOnInit(): void {
    this.loadLogFiles();
  }

  loadLogFiles(): void {
    this.loading = true;

    // Check if we should use mock data
    if (shouldUseMockData()) {
      // Mock data response with proper typing
      const mockResponse = mockLogsData as LogFilesResponse;

      // Simulate API delay for realistic behavior
      setTimeout(() => {
        this.logFiles = mockResponse.log_files;
        this.totalFiles = mockResponse.total_count;
        this.applySearch();
        this.loading = false;
        this.refreshing = false;
      }, 500);

      return;
    }

    // Normal API call flow
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
        this.toast.error('Failed to load log files. Please try again.');
        this.loading = false;
        this.refreshing = false;
      },
    });
  }

  refresh(): void {
    this.refreshing = true;
    this.loadLogFiles();
  }

  applySearch(): void {
    const term = this.searchTerm.trim().toLowerCase();
    const now = new Date();
    const sevenDaysMs = 7 * 24 * 60 * 60 * 1000;

    // Filter by search term
    let result = this.logFiles.filter((file) => {
      if (!term) return true;
      return (
        file.filename.toLowerCase().includes(term) ||
        (file.date || '').toLowerCase().includes(term)
      );
    });

    // Filter recent only
    if (this.showRecentOnly) {
      result = result.filter((file) => {
        const d = new Date(file.last_modified).getTime();
        return !isNaN(d) && now.getTime() - d <= sevenDaysMs;
      });
    }

    // Sort
    result.sort((a, b) => this.compareFiles(a, b));

    this.filteredLogFiles = result;
  }

  private compareFiles(a: LogFile, b: LogFile): number {
    let cmp = 0;
    switch (this.sortBy) {
      case 'size':
        cmp = (a.size || 0) - (b.size || 0);
        break;
      case 'filename':
        cmp = a.filename.localeCompare(b.filename, undefined, {
          sensitivity: 'base',
        });
        break;
      case 'date':
        // Compare by provided date string if valid; fallback to last_modified
        cmp =
          (new Date(a.date).getTime() || new Date(a.last_modified).getTime()) -
          (new Date(b.date).getTime() || new Date(b.last_modified).getTime());
        break;
      case 'last_modified':
      default:
        cmp =
          new Date(a.last_modified).getTime() -
          new Date(b.last_modified).getTime();
        break;
    }
    return this.sortDir === 'asc' ? cmp : -cmp;
  }

  setSort(by: 'last_modified' | 'size' | 'filename' | 'date'): void {
    if (this.sortBy === by) {
      this.sortDir = this.sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      this.sortBy = by;
      this.sortDir = by === 'filename' ? 'asc' : 'desc';
    }
    this.applySearch();
  }

  toggleRecentOnly(): void {
    this.showRecentOnly = !this.showRecentOnly;
    this.applySearch();
  }

  onSearchChange(): void {
    this.applySearch();
  }

  clearSearch(): void {
    this.searchTerm = '';
    this.applySearch();
  }

  viewLogFile(filename: string): void {
    if (shouldUseMockData()) {
      this.toast.info('Log file viewing is disabled in the guest environment.');
      return;
    }

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
      minute: '2-digit',
    });
  }

  formatRelative(dateString: string): string {
    const d = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    if (isNaN(diffMs)) return '—';
    const diffMin = Math.floor(diffMs / (1000 * 60));
    if (diffMin < 1) return 'just now';
    if (diffMin < 60) return `${diffMin} min ago`;
    const diffH = Math.floor(diffMin / 60);
    if (diffH < 24) return `${diffH}h ago`;
    const diffD = Math.floor(diffH / 24);
    if (diffD < 7) return `${diffD}d ago`;
    return this.formatDate(dateString);
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
