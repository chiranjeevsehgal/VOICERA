import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  IPCredit,
  CreditService,
} from '../../../services/admin/credit.service';
import { HotToastService } from '@ngxpert/hot-toast';
import { shouldUseMockData } from '../../../utils/role.utils';
import * as mockCreditData from '../../../utils/mockData/mockIps.json';
import { CreditRequestsModalComponent } from '../credit-requests-modal/credit-requests-modal.component';

@Component({
  selector: 'app-credit-management',
  standalone: true,
  imports: [CommonModule, FormsModule, CreditRequestsModalComponent],
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
  totalCount: number = 0;
  showEditModal: boolean = false;
  creditToEdit: IPCredit | null = null;
  newCreditAmount: number = 0;
  updatingCredits: boolean = false;
showCreditRequestsModal: boolean = false;

  constructor(
    private creditService: CreditService,
    private toast: HotToastService,
  ) {}

  ngOnInit() {
    this.loadCredits();
  }

  loadCredits() {
    this.loading = true;

    // Check if we should use mock data
    if (shouldUseMockData()) {
      // Mock data response with proper typing
      const mockResponse = mockCreditData as any;

      // Process mock data the same way as API response
      this.totalCount = mockResponse.total_count;
      this.credits = mockResponse.ip_credits.map((apiCredit: any) =>
        this.creditService.transformApiCredit(apiCredit),
      );
      this.filteredCredits = [...this.credits];
      this.loading = false;
      this.refreshing = false;

      return;
    }

    // Normal API call flow
    this.creditService.getIPCredits().subscribe({
      next: (response) => {
        this.totalCount = response.total_count;
        this.credits = response.ip_credits.map((apiCredit) =>
          this.creditService.transformApiCredit(apiCredit),
        );
        this.filteredCredits = [...this.credits];
        this.loading = false;
        this.refreshing = false;
      },
      error: (error) => {
        console.error('Error loading IP credits:', error);
        this.toast.error('Failed to load IP credits. Please try again.');
        this.loading = false;


        this.credits = [];
        this.filteredCredits = [];
      },
    });
  }

  filterCredits() {
    this.filteredCredits = this.credits.filter((credit) => {
      const matchesSearch = credit.ip
        .toLowerCase()
        .includes(this.searchQuery.toLowerCase());
      return matchesSearch;
    });
  }

  formatLastUsed(date: Date): string {
    const now = new Date();
    const diffInHours = Math.floor(
      (now.getTime() - date.getTime()) / (1000 * 60 * 60),
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

  openEditModal(credit: IPCredit) {
    if (shouldUseMockData()) {
      this.toast.info(
        'Credit modifications are disabled in the guest environment.',
      );
      return;
    }

    this.creditToEdit = credit;
    this.newCreditAmount = credit.credits;
    this.showEditModal = true;
  }

  closeEditModal() {
    this.showEditModal = false;
    this.creditToEdit = null;
    this.newCreditAmount = 0;
    this.updatingCredits = false;
  }

  confirmUpdateCredits() {
    if (!this.creditToEdit || this.newCreditAmount < 0) return;

    // Additional check in case modal somehow opened in mock mode
    if (shouldUseMockData()) {
      this.toast.info(
        'Credit modifications are disabled in the guest environment.',
      );
      this.closeEditModal();
      return;
    }

    this.updatingCredits = true;

    this.creditService
      .updateIPCredits(this.creditToEdit.ip, this.newCreditAmount)
      .subscribe({
        next: (response) => {
          // Update the credit in local arrays
          const creditIndex = this.credits.findIndex(
            (c) => c.id === this.creditToEdit!.id,
          );
          if (creditIndex !== -1) {
            this.credits[creditIndex].credits = response.new_credits;
            // Update filtered credits as well
            const filteredIndex = this.filteredCredits.findIndex(
              (c) => c.id === this.creditToEdit!.id,
            );
            if (filteredIndex !== -1) {
              this.filteredCredits[filteredIndex].credits =
                response.new_credits;
            }
          }

          this.toast.success(
            `Credits updated successfully for ${this.creditToEdit!.ip}`,
          );
          this.closeEditModal();
        },
        error: (error) => {
          console.error('Error updating credits:', error);
          this.toast.error('Failed to update credits. Please try again.');
          this.updatingCredits = false;
        },
      });
  }

  openCreditRequestsModal(): void {
  this.showCreditRequestsModal = true;
}

closeCreditRequestsModal(): void {
  this.showCreditRequestsModal = false;
}
}
