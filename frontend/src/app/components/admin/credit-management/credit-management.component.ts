import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClientModule } from '@angular/common/http';
import { IPCredit, CreditService } from '../../../services/admin/credit.service';
import { HotToastService } from '@ngxpert/hot-toast';

@Component({
  selector: 'app-credit-management',
  standalone: true,
  imports: [CommonModule, FormsModule, HttpClientModule],
  providers: [CreditService],
  templateUrl: './credit-management.component.html',
  styles: ``,
})
export class CreditManagementComponent implements OnInit {
  credits: IPCredit[] = [];
  filteredCredits: IPCredit[] = [];
  searchQuery: string = '';
  selectedCreditRange: string = 'all';
  loading: boolean = false;
  refreshing: boolean = false;
  error: string = '';
  totalCount: number = 0;

  constructor(
    private creditService: CreditService,
    private toast:HotToastService
  ) {}

  ngOnInit() {
    this.loadCredits();
  }

  loadCredits() {
    this.loading = true;
    this.error = '';

    this.creditService.getIPCredits().subscribe({
      next: (response) => {
        this.totalCount = response.total_count;
        this.credits = response.ip_credits.map((apiCredit) =>
          this.creditService.transformApiCredit(apiCredit)
        );
        this.filteredCredits = [...this.credits];
        this.loading = false;
        this.refreshing = false;
      },
      error: (error) => {
        console.error('Error loading IP credits:', error);
        this.error = 'Failed to load IP credits. Please try again.';
        this.loading = false;

        this.toast.error('Failed to load IP credits. Please try again.');

        this.credits = [];
        this.filteredCredits = [];
      },
    });
  }

  filterCredits() {
    this.filteredCredits = this.credits.filter((credit) => {
      const matchesSearch = credit.ip.toLowerCase().includes(this.searchQuery.toLowerCase());
      return matchesSearch;
    });
  }

  formatLastUsed(date: Date): string {
    const now = new Date();
    const diffInHours = Math.floor(
      (now.getTime() - date.getTime()) / (1000 * 60 * 60)
    );

    if (diffInHours < 1) return 'Just now';
    if (diffInHours < 24) return `${diffInHours}h ago`;

    const diffInDays = Math.floor(diffInHours / 24);
    if (diffInDays < 30) return `${diffInDays}d ago`;

    const diffInMonths = Math.floor(diffInDays / 30);
    return `${diffInMonths}mo ago`;
  }

  formatCreatedAt(date: Date): string {
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  }

  refreshCredits() {
    this.refreshing = true;
    this.loadCredits();
  }

  trackCreditById(index: number, credit: IPCredit): string {
    return credit.id;
  }
}