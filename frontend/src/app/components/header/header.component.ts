import { Component, OnInit, OnDestroy, HostListener } from '@angular/core';
import { Router } from '@angular/router';
import {
  ProfileService,
  UserProfile,
} from '../../services/auth/profile.service';
import { Subject, takeUntil } from 'rxjs';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-header',
  imports: [CommonModule, FormsModule],
  templateUrl: './header.component.html',
  styles: ``,
})
export class HeaderComponent implements OnInit, OnDestroy {
  userProfile: UserProfile | null = null;
  credits: number = 0;
  userInitials: string = '';
  showProfileDropdown: boolean = false;
  isLoadingProfile: boolean = true;
  isLoadingCredits: boolean = true;

  private destroy$ = new Subject<void>();

  constructor(private router: Router, private profileService: ProfileService) {}

  ngOnInit(): void {
    this.loadUserData();
    this.subscribeToProfileData();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  // Listen for clicks outside the component
  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    const target = event.target as HTMLElement;
    const profileDropdown = document.querySelector('.relative') as HTMLElement;

    if (profileDropdown && !profileDropdown.contains(target)) {
      this.showProfileDropdown = false;
    }
  }

  onAISearchClick(): void {
    this.router.navigate(['/ai-search']);
  }

  onUploadClick(): void {
    this.router.navigate(['/upload']);
  }

  onLibraryClick(): void {
    this.router.navigate(['/search']);
  }

  private loadUserData(): void {
    this.profileService.loadUserData();
  }

  private subscribeToProfileData(): void {
    // Subscribe to user profile changes
    this.profileService.userProfile$
      .pipe(takeUntil(this.destroy$))
      .subscribe((profile) => {
        this.userProfile = profile;
        if (profile) {
          this.userInitials = this.profileService.getUserInitials(
            profile.full_name
          );
          this.isLoadingProfile = false;
        }
      });

    // Subscribe to credits changes
    this.profileService.credits$
      .pipe(takeUntil(this.destroy$))
      .subscribe((credits) => {
        this.credits = credits;
        this.isLoadingCredits = false;
      });
  }

  onProfileClick(): void {
    this.showProfileDropdown = !this.showProfileDropdown;
  }

  onProfileDropdownClose(): void {
    this.showProfileDropdown = false;
  }

  onSignOut(): void {
    localStorage.removeItem('vEra_auth_token');
    localStorage.removeItem('vEra_user_profile');
    this.router.navigate(['/login']);
  }
}
