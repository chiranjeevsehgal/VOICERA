import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, OnInit, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { UserProfile } from '../../services/auth/profile.service';

export interface CreditRequestData {
  userInfo: {
    full_name: string;
    email: string;
    role: string;
  };
  reason: string;
}

@Component({
  selector: 'app-request-credits-modal',
  imports: [CommonModule, FormsModule],
  templateUrl: './request-credits-modal.component.html',
  styles: ``
})
export class RequestCreditsModalComponent implements OnInit {
  @Input() isVisible: boolean = false;
  @Input() userProfile: UserProfile | null = null;
  @Input() userInitials: string = '';
  @Input() isSubmitting: boolean = false;
  @Output() closeModal = new EventEmitter<void>();
  @Output() submitRequest = new EventEmitter<CreditRequestData>();
  
  reason: string = '';

  ngOnInit() {
    // Focus on textarea when modal opens
    if (this.isVisible) {
      setTimeout(() => {
        const textarea = document.getElementById('reason');
        if (textarea) {
          textarea.focus();
        }
      }, 300);
    }
  }

  onBackdropClick(event: Event) {
    if (event.target === event.currentTarget) {
      this.onClose();
    }
  }

  onClose() {
    this.closeModal.emit();
    this.resetForm();
  }

  async onSubmit() {
    if (!this.userProfile || this.reason.trim().length < 5 || this.isSubmitting) {
      return;
    }

    this.isSubmitting = true;

    try {
      const requestData: CreditRequestData = {
        userInfo: {
          full_name: this.userProfile.full_name,
          email: this.userProfile.email,
          role: this.userProfile.role,
        },
        reason: this.reason.trim()
      };

      this.submitRequest.emit(requestData);
    } catch (error) {
      console.error('Error submitting credit request:', error);
      this.isSubmitting = false;
    }
  }

  resetForm() {
    this.reason = '';
    this.isSubmitting = false;
  }

  // Handle escape key
  onKeyDown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      this.onClose();
    }
  }
}