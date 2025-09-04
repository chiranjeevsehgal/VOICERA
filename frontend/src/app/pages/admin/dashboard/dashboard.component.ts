import { Component, HostListener, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SidebarComponent } from '../../../components/admin/sidebar/sidebar.component';
import { UserManagementComponent } from '../../../components/admin/user-management/user-management.component';
import { AdminAuthService } from '../../../services/admin/admin.auth.service';
import { Subject, takeUntil } from 'rxjs';
import { UserProfile } from '../../../services/auth/profile.service';
import { CreditManagementComponent } from '../../../components/admin/credit-management/credit-management.component';
import { AudioManagementComponent } from '../../../components/admin/audio-management/audio-management.component';
import { UsageLogsComponent } from '../../../components/admin/usage-logs/usage-logs.component';

@Component({
  selector: 'app-dashboard',
  imports: [CommonModule, SidebarComponent, UserManagementComponent, CreditManagementComponent, AudioManagementComponent, UsageLogsComponent],
  templateUrl: './dashboard.component.html',
  styles: ``
})
export class AdminDashboardComponent implements OnInit, OnDestroy  {
  
  // Sidebar state management
  isSidebarOpen: boolean = false;
  isMobile: boolean = false;
  currentView: string = 'user-management';
  userProfile: UserProfile | null = null;
  userInitials: string = 'A';
  isLoadingProfile: boolean = true;
  private destroy$ = new Subject<void>();

  private readonly CURRENT_VIEW_KEY = 'vEra_admin_current-view';
  
  // Responsive breakpoint detection
  @HostListener('window:resize', ['$event'])
  onResize(event: any) {
    this.checkScreenSize();
  }

  constructor(private adminService: AdminAuthService) {}

  ngOnInit() {
    this.checkScreenSize();
    this.loadCurrentView();
    this.loadUserData();
    this.subscribeToProfileData(); 
  }

  ngOnDestroy() {
    this.destroy$.next();
    this.destroy$.complete();
  }

  private subscribeToProfileData(): void {
    this.adminService.userProfile$
      .pipe(takeUntil(this.destroy$))
      .subscribe((profile) => {
        this.userProfile = profile;
        if (profile) {
          this.userInitials = this.getUserInitials(profile.full_name);
          this.isLoadingProfile = false;
        }
      });
  }

  private getUserInitials(fullName: string): string {
    if (!fullName) return 'A';
    const names = fullName.trim().split(' ');
    if (names.length === 1) {
      return names[0].charAt(0).toUpperCase();
    }
    return (names[0].charAt(0) + names[names.length - 1].charAt(0)).toUpperCase();
  }

  private loadCurrentView(): void {
    // Try to get the last viewed page from localStorage
    const savedView = localStorage.getItem(this.CURRENT_VIEW_KEY);
    if (savedView && this.isValidView(savedView)) {
      this.currentView = savedView;
    }
    // If no saved view or invalid view, it will remain 'user-management'
  }

  private saveCurrentView(): void {
    localStorage.setItem(this.CURRENT_VIEW_KEY, this.currentView);
  }
  
  private loadUserData(): void {
    this.adminService.loadUserData();
  }

  private isValidView(view: string): boolean {
    const validViews = [
      'user-management', 
      'audio-management',
      'credit-management',
      'logs',
    ];
    return validViews.includes(view);
  }

  private checkScreenSize(): void {
    this.isMobile = window.innerWidth < 1024; // lg breakpoint
    // Auto-close sidebar on mobile when switching to mobile view
    if (this.isMobile) {
      this.isSidebarOpen = false;
    } else {
      // Auto-open sidebar on desktop
      this.isSidebarOpen = true;
    }
  }

  toggleSidebar(): void {
    this.isSidebarOpen = !this.isSidebarOpen;
  }

  onSidebarItemSelected(itemId: string): void {
    this.currentView = itemId;
    this.saveCurrentView(); // Save the view whenever it changes
  }

  // Helper method to get page title
  getPageTitle(): string {
    const titles: { [key: string]: string } = {
      'user-management': 'User Management',
      'credit-management': 'Credits',
      'audio-management': 'Audio Management',
      'logs': 'Logs',
    };
    return titles[this.currentView] || 'Dashboard';
  }

  // Helper method to get page description
  getPageDescription(): string {
    const descriptions: { [key: string]: string } = {
      'user-management': 'Manage user accounts',
      'credit-management': 'Manage IP credits',
      'audio-management': 'Upload, organize and manage audio content',
      'logs': 'View API usage metrics and endpoint counts',
    };
    return descriptions[this.currentView] || 'Manage your application';
  }
}