import {
  Component,
  Input,
  Output,
  EventEmitter,
  OnInit,
  OnChanges,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  CreditService,
  CreditRequest,
  CreditRequestUser,
} from '../../../services/admin/credit.service';
import { FormsModule } from '@angular/forms';
import { HotToastService } from '@ngxpert/hot-toast';
import { shouldUseMockData } from '../../../utils/role.utils';
import * as mockCreditRequestsData from '../../../utils/mockData/mockCreditRequests.json';

@Component({
  selector: 'app-credit-requests-modal',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './credit-requests-modal.component.html',
})
export class CreditRequestsModalComponent implements OnInit, OnChanges {
  @Input() isVisible: boolean = false;
  @Output() closeModal = new EventEmitter<void>();

  creditRequests: CreditRequest[] = [];
  loading: boolean = false;

  constructor(
    private creditService: CreditService,
    private toast: HotToastService
  ) {}

  ngOnInit() {
    if (this.isVisible) {
      this.loadRequests();
    }
  }

  ngOnChanges() {
    if (this.isVisible && this.creditRequests.length === 0) {
      this.loadRequests();
    }
  }

  onBackdropClick(event: Event) {
    if (event.target === event.currentTarget) {
      this.onClose();
    }
  }

  onClose() {
    this.closeModal.emit();
  }

  loadRequests() {
    this.loading = true;

    // Check if we should use mock data
    if (shouldUseMockData()) {
      // Mock data response with proper typing
      const mockResponse = mockCreditRequestsData as any;

      // Process mock data the same way as API response
      this.creditRequests = mockResponse.requests.map((request: any) =>
        this.creditService.transformApiCreditRequest(request)
      );
      this.loading = false;
      return;
    }

    // Normal API call flow
    this.creditService.getCreditRequests().subscribe({
      next: (response) => {
        this.creditRequests = response.requests.map((request) =>
          this.creditService.transformApiCreditRequest(request)
        );
        this.loading = false;
      },
      error: (error) => {
        console.error('Error loading credit requests:', error);
        this.loading = false;
        this.creditRequests = [];
      },
    });
  }

  refreshRequests() {
    this.loadRequests();
  }

  getInitials(fullName: string): string {
    return fullName
      .split(' ')
      .map((name) => name.charAt(0))
      .join('')
      .toUpperCase()
      .substring(0, 2);
  }

  getStatusClasses(status: string): string {
    switch (status) {
      case 'pending':
        return 'bg-yellow-100 text-yellow-800';
      case 'approved':
        return 'bg-green-100 text-green-800';
      case 'rejected':
        return 'bg-red-100 text-red-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  }

  formatDate(date: Date): string {
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  trackRequestById(index: number, request: CreditRequest): string {
    return request.id;
  }

  onApproveClick(requestId: string): void {
    // Block action for guest users
    if (shouldUseMockData()) {
      this.toast.info(
        'Credit request modifications are disabled in the guest environment.'
      );
      return;
    }

    // Find the request and set showApproveInput to true
    const request = this.creditRequests.find((r) => r.id === requestId);
    if (request) {
      request.showApproveInput = true;
      request.creditsToAdd = 100; // Default value
    }
  }

  onCancelApprove(requestId: string): void {
    // Find the request and hide the approve input
    const request = this.creditRequests.find((r) => r.id === requestId);
    if (request) {
      request.showApproveInput = false;
      request.creditsToAdd = undefined;
    }
  }

  onConfirmApprove(requestId: string, creditsToAdd: number): void {
    // Additional check in case action somehow triggered in mock mode
    if (shouldUseMockData()) {
      this.toast.info(
        'Credit request modifications are disabled in the guest environment.'
      );
      return;
    }

    if (!creditsToAdd || creditsToAdd < 1) {
      return;
    }

    const request = this.creditRequests.find((r) => r.id === requestId);
    if (!request) return;

    request.isProcessing = true;

    this.creditService
      .updateCreditRequest(requestId, 'approve', creditsToAdd)
      .subscribe({
        next: (response) => {
          this.toast.success('Request approved successfully.');
          request.status = 'approved';
          request.updatedAt = new Date();
          request.showApproveInput = false;
          request.creditsToAdd = undefined;
          request.isProcessing = false;

          this.loadRequests();
        },
        error: (error) => {
          console.error('Error approving request:', error);
          request.isProcessing = false;
          this.toast.error('Failed to approve request. Please try again.');
        },
      });
  }

  onReject(requestId: string): void {
    // Block action for guest users
    if (shouldUseMockData()) {
      this.toast.info(
        'Credit request modifications are disabled in the guest environment.'
      );
      return;
    }

    const request = this.creditRequests.find((r) => r.id === requestId);
    if (!request) return;

    request.isProcessing = true;

    this.creditService.updateCreditRequest(requestId, 'reject').subscribe({
      next: (response) => {
        this.toast.success('Request rejected successfully.');
        request.status = 'rejected';
        request.updatedAt = new Date();
        request.isProcessing = false;

        this.loadRequests();
      },
      error: (error) => {
        console.error('Error rejecting request:', error);
        request.isProcessing = false;

        this.toast.error('Failed to reject request. Please try again.');
      },
    });
  }
}