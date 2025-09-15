import {
  Component,
  OnInit,
  OnDestroy,
  HostListener,
  ViewChild,
  ElementRef,
} from '@angular/core';
import { Router } from '@angular/router';
import { RouterModule } from '@angular/router';
import {
  ProfileService,
  UserProfile,
} from '../../services/auth/profile.service';
import { Subject, takeUntil } from 'rxjs';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { getCurrentUserRole } from '../../utils/role.utils';
import { ArrowRight, LogOut, LucideAngularModule } from 'lucide-angular';
import { CreditRequestService } from '../../services/credit-request.service';
import { HotToastService } from '@ngxpert/hot-toast';
import {
  CreditRequestData,
  RequestCreditsModalComponent,
} from '../request-credits-modal/request-credits-modal.component';

@Component({
  selector: 'app-header',
  imports: [
    CommonModule,
    FormsModule,
    RouterModule,
    LucideAngularModule,
    RequestCreditsModalComponent,
  ],
  templateUrl: './header.component.html',
  styles: ``,
})
export class HeaderComponent implements OnInit, OnDestroy {
  @ViewChild('mobileMenuButton') mobileMenuButton!: ElementRef;
  @ViewChild('mobileMenu') mobileMenu!: ElementRef;
  @ViewChild('profileDropdown') profileDropdown!: ElementRef;
  @ViewChild('mobileProfileDropdown') mobileProfileDropdown!: ElementRef;
  @ViewChild(RequestCreditsModalComponent)
  requestCreditsModal!: RequestCreditsModalComponent;
  @ViewChild('navMenuContainer') navMenuContainer!: ElementRef;
  readonly ArrowRight = ArrowRight;
  readonly LogOut = LogOut;
  userProfile: UserProfile | null = null;
  credits: number = 0;
  userInitials: string = '';
  showProfileDropdown: boolean = false;
  showMobileMenu: boolean = false;
  showNavDropdown: boolean = false;
  isLoadingProfile: boolean = true;
  isLoadingCredits: boolean = true;
  userRole: string = '';
  showRequestCreditsModal: boolean = false;
  isSubmittingCreditRequest: boolean = false;

  navItems: Array<{
    label: string;
    route: string;
    icon: 'library' | 'search' | 'upload' | 'admin';
    requiresAdmin?: boolean;
    description?: string;
  }> = [
    {
      label: 'Library',
      route: '/library',
      icon: 'library',
      description: 'Browse your transcripts and podcasts',
    },
    {
      label: 'AI Search',
      route: '/ai-search',
      icon: 'search',
      description: 'Search accurate content with natural language',
    },
    {
      label: 'Upload',
      route: '/upload',
      icon: 'upload',
      description: 'Add new audio or files',
    },
    {
      label: 'Admin',
      route: '/admin/dashboard',
      icon: 'admin',
      requiresAdmin: true,
      description: 'Manage users and system settings',
    },
  ];

  private destroy$ = new Subject<void>();

  constructor(
    private router: Router,
    private profileService: ProfileService,
    private creditRequestService: CreditRequestService,
    private toast: HotToastService
  ) {}

  ngOnInit(): void {
    this.loadUserData();
    this.subscribeToProfileData();
    this.userRole = getCurrentUserRole() || '';
  }

  // Method to navigate to admin side
  navigateToAdminSide(): void {
    this.router.navigate(['/admin/dashboard']);
  }

  // Method to check if user can access admin side
  canAccessAdminSide(): boolean {
    return this.userRole === 'admin' || this.userRole === 'guest';
  }

  // ... rest of your existing methods remain unchanged
  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    const target = event.target as HTMLElement;

    // Handle profile dropdown clicks
    if (
      this.profileDropdown &&
      !this.profileDropdown.nativeElement.contains(target) &&
      this.mobileProfileDropdown &&
      !this.mobileProfileDropdown.nativeElement.contains(target)
    ) {
      this.showProfileDropdown = false;
    }

    // Handle mobile menu clicks
    if (
      this.showMobileMenu &&
      this.mobileMenuButton &&
      !this.mobileMenuButton.nativeElement.contains(target) &&
      this.mobileMenu &&
      !this.mobileMenu.nativeElement.contains(target)
    ) {
      this.showMobileMenu = false;
    }

    // Handle nav dropdown clicks
    if (
      this.showNavDropdown &&
      this.navMenuContainer &&
      !this.navMenuContainer.nativeElement.contains(target)
    ) {
      this.showNavDropdown = false;
    }
  }

  @HostListener('window:resize', ['$event'])
  onResize(event: any): void {
    if (event.target.innerWidth >= 768) {
      this.showMobileMenu = false;
    }
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.showNavDropdown = false;
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
      this.showNavDropdown = false;
    }
  }

  closeMobileMenu(): void {
    this.showMobileMenu = false;
  }

  toggleNavDropdown(): void {
    this.showNavDropdown = !this.showNavDropdown;
    if (this.showNavDropdown) {
      this.showProfileDropdown = false;
      this.showMobileMenu = false;
    }
  }

  goTo(route: string): void {
    this.showNavDropdown = false;
    this.router.navigate([route]);
  }

  isActiveRoute(route: string): boolean {
    return this.router.url === route || this.router.url.startsWith(route + '/');
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
    localStorage.removeItem('vEra_admin_current-view');

    this.router.navigate(['/login'], {
      queryParams: { loggedOut: 'true' },
    });
  }

  onLogoClick(): void {
    this.router.navigate(['/library']);
  }

  onRequestCredits(): void {
    this.showRequestCreditsModal = true;
    this.showProfileDropdown = false; // Close profile dropdown
  }

  onCloseRequestCreditsModal(): void {
    this.showRequestCreditsModal = false;
  }

  async onSubmitCreditRequest(requestData: CreditRequestData): Promise<void> {
    this.isSubmittingCreditRequest = true;
    try {
      await this.creditRequestService.requestCredits(requestData).toPromise();

      this.toast.success(
        "We've received your credit request and will review it soon. You'll hear back from us within 24 hours."
      );

      this.showRequestCreditsModal = false;
      if (this.requestCreditsModal) {
        this.requestCreditsModal.resetForm();
      }
    } catch (error: any) {
      console.error('Error submitting credit request:', error);

      const errorMessage =
        error?.error?.detail ||
        "Sorry, we couldn't process your request right now. Please try again later.";

      this.toast.error(errorMessage);
    } finally {
      this.isSubmittingCreditRequest = false;
    }
  }
}
