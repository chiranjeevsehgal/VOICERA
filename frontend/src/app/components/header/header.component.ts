import { Component, OnInit, OnDestroy, HostListener, ViewChild, ElementRef } from '@angular/core';
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
  @ViewChild('mobileMenuButton') mobileMenuButton!: ElementRef;
  @ViewChild('mobileMenu') mobileMenu!: ElementRef;
  @ViewChild('profileDropdown') profileDropdown!: ElementRef;
  @ViewChild('mobileProfileDropdown') mobileProfileDropdown!: ElementRef;

  userProfile: UserProfile | null = null;
  credits: number = 0;
  userInitials: string = '';
  showProfileDropdown: boolean = false;
  showMobileMenu: boolean = false;
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

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    const target = event.target as HTMLElement;

    // Handle profile dropdown clicks
    if (this.profileDropdown && !this.profileDropdown.nativeElement.contains(target) &&
        this.mobileProfileDropdown && !this.mobileProfileDropdown.nativeElement.contains(target)) {
      this.showProfileDropdown = false;
    }

    // Handle mobile menu clicks
    if (this.showMobileMenu && 
        this.mobileMenuButton && !this.mobileMenuButton.nativeElement.contains(target) &&
        this.mobileMenu && !this.mobileMenu.nativeElement.contains(target)) {
      this.showMobileMenu = false;
    }
  }

  @HostListener('window:resize', ['$event'])
  onResize(event: any): void {
    if (event.target.innerWidth >= 768) {
      this.showMobileMenu = false;
    }
  }

  onAISearchClick(): void {
    this.router.navigate(['/ai-search']);
  }

  onUploadClick(): void {
    this.router.navigate(['/upload']);
  }

  onLibraryClick(): void {
    this.router.navigate(['/library']);
  }

  toggleMobileMenu(): void {
    this.showMobileMenu = !this.showMobileMenu;
    
    if (this.showMobileMenu) {
      this.showProfileDropdown = false;
    }
  }

  closeMobileMenu(): void {
    this.showMobileMenu = false;
  }

  private loadUserData(): void {
    this.profileService.loadUserData();
  }

  private subscribeToProfileData(): void {
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

    this.profileService.credits$
      .pipe(takeUntil(this.destroy$))
      .subscribe((credits) => {
        this.credits = credits;
        this.isLoadingCredits = false;
      });
  }

  onProfileClick(): void {
    this.showProfileDropdown = !this.showProfileDropdown;
    
    if (this.showProfileDropdown) {
      this.showMobileMenu = false;
    }
  }

  onProfileDropdownClose(): void {
    this.showProfileDropdown = false;
  }

  onSignOut(): void {
    this.showProfileDropdown = false;
    this.showMobileMenu = false;
    
    localStorage.removeItem('vEra_auth_token');
    localStorage.removeItem('vEra_user_profile');
    this.router.navigate(['/login']);
  }
}