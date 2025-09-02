import { Component, HostListener, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SidebarComponent } from '../../../components/admin/sidebar/sidebar.component';

@Component({
  selector: 'app-dashboard',
  imports: [CommonModule, SidebarComponent],
  templateUrl: './dashboard.component.html',
  styles: ``
})
export class AdminDashboardComponent implements OnInit {
  
  // Sidebar state management
  isSidebarOpen: boolean = false;
  isMobile: boolean = false;
  currentView: string = 'dashboard';
  
  // Responsive breakpoint detection
  @HostListener('window:resize', ['$event'])
  onResize(event: any) {
    this.checkScreenSize();
  }

  ngOnInit() {
    this.checkScreenSize();
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
    console.log('Selected view:', itemId);
  }

  // Helper method to get page title
  getPageTitle(): string {
    const titles: { [key: string]: string } = {
      'dashboard': 'Dashboard Overview',
      'user-management': 'User Management',
      'audio-management': 'Audio Management',
      'search-analytics': 'Search Analytics',
      'ai-configuration': 'AI Configuration',
      'system-settings': 'System Settings',
      'reports': 'Reports & Logs'
    };
    return titles[this.currentView] || 'Dashboard';
  }

  // Helper method to get page description
  getPageDescription(): string {
    const descriptions: { [key: string]: string } = {
      'dashboard': 'Welcome to your audio search admin dashboard',
      'user-management': 'Manage user accounts, roles and permissions',
      'audio-management': 'Upload, organize and manage audio content',
      'search-analytics': 'View search performance and user behavior',
      'ai-configuration': 'Configure AI models and search parameters',
      'system-settings': 'System configuration and preferences',
      'reports': 'Generate reports and view system logs'
    };
    return descriptions[this.currentView] || 'Manage your application';
  }

  // Helper method to get page icon
  getPageIcon(): string {
    const icons: { [key: string]: string } = {
      'dashboard': 'M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2H5a2 2 0 00-2-2z M3 7l9 6 9-6',
      'user-management': 'M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197m13.5-9a2.5 2.5 0 11-5 0 2.5 2.5 0 015 0z',
      'audio-management': 'M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M9 21H5a2 2 0 01-2-2V9a2 2 0 012-2h4l7 7-7 7z',
      'search-analytics': 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2H9a2 2 0 00-2 2z',
      'ai-configuration': 'M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z',
      'system-settings': 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z',
      'reports': 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z'
    };
    return icons[this.currentView] || icons['dashboard'];
  }
}