import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClientModule } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { LogsService, LogContentResponse } from '../../../services/admin/logs.service';

@Component({
  selector: 'app-log-viewer',
  standalone: true,
  imports: [CommonModule, HttpClientModule, FormsModule],
  providers: [LogsService],
  templateUrl: './log-viewer.component.html',
  styles: ``
})
export class LogViewerComponent implements OnInit {
  loading = false;
  refreshing = false;
  error = '';
  
  filename = '';
  logContent: LogContentResponse | null = null;
  
  // Filters
  searchTerm = '';
  lineLimit = 1000;
  showFilters = false;
  
  // Display options
  wrapLines = false;
  showLineNumbers = true;
  fontSize = 'text-sm';
  
  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private logsService: LogsService
  ) {}

  ngOnInit(): void {
    this.route.params.subscribe(params => {
      this.filename = params['filename'];
      if (this.filename) {
        this.loadLogContent();
      }
    });
  }

  loadLogContent(): void {
    this.loading = true;
    this.error = '';
    
    const lines = this.lineLimit > 0 ? this.lineLimit : undefined;
    const search = this.searchTerm.trim() || undefined;
    
    this.logsService.getLogFileContent(this.filename, lines, search).subscribe({
      next: (response: LogContentResponse) => {
        this.logContent = response;
        this.loading = false;
        this.refreshing = false;
      },
      error: (err) => {
        console.error('Failed to load log content', err);
        this.error = 'Failed to load log content. Please try again.';
        this.loading = false;
        this.refreshing = false;
      }
    });
  }

  refresh(): void {
    this.refreshing = true;
    this.loadLogContent();
  }

  applyFilters(): void {
    this.loadLogContent();
  }

  clearFilters(): void {
    this.searchTerm = '';
    this.lineLimit = 1000;
    this.loadLogContent();
  }

  toggleFilters(): void {
    this.showFilters = !this.showFilters;
  }

  goBack(): void {
    this.router.navigate(['/admin/application-logs']);
  }

  downloadLog(): void {
    if (!this.logContent) return;
    
    const blob = new Blob([this.logContent.content], { type: 'text/plain' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = this.filename;
    link.click();
    window.URL.revokeObjectURL(url);
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
      second: '2-digit'
    });
  }

  getLogLines(): string[] {
    if (!this.logContent?.content) return [];
    return this.logContent.content.split('\n');
  }

  highlightSearchTerm(line: string): string {
    if (!this.searchTerm.trim()) return line;
    
    const regex = new RegExp(`(${this.escapeRegExp(this.searchTerm)})`, 'gi');
    return line.replace(regex, '<mark class="bg-yellow-400 text-gray-900 px-1 rounded font-semibold">$1</mark>');
  }

  private escapeRegExp(string: string): string {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  getLineClass(line: string): string {
    const lowerLine = line.toLowerCase();
    
    if (lowerLine.includes('error') || lowerLine.includes('exception') || lowerLine.includes('failed')) {
      return 'text-red-400 bg-red-900/20 border-l-2 border-red-400';
    }
    if (lowerLine.includes('warning') || lowerLine.includes('warn')) {
      return 'text-yellow-300 bg-yellow-900/20 border-l-2 border-yellow-400';
    }
    if (lowerLine.includes('info') || lowerLine.includes('success')) {
      return 'text-blue-300 bg-blue-900/20 border-l-2 border-blue-400';
    }
    if (lowerLine.includes('debug')) {
      return 'text-gray-400';
    }
    
    return 'text-gray-200';
  }

  copyToClipboard(): void {
    if (!this.logContent?.content) return;
    
    navigator.clipboard.writeText(this.logContent.content).then(() => {
      // Could add a toast notification here
    }).catch(err => {
      console.error('Failed to copy to clipboard', err);
    });
  }
}
