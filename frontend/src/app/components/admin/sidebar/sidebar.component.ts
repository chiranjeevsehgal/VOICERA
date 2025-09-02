// sidebar.component.ts
import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
// Remove Router import - we don't need it anymore

export interface SidebarItem {
  id: string;
  label: string;
  icon: string;
  active?: boolean;
  badge?: number;
  // Remove route property - not needed
}

@Component({
  selector: 'app-sidebar',
  imports: [CommonModule, FormsModule],
  templateUrl: './sidebar.component.html',
  styles: ``,
})
export class SidebarComponent {
  @Input() isOpen: boolean = false;
  @Input() isMobile: boolean = false;
  @Input() currentView: string = 'dashboard'; // Add this to sync with parent
  @Output() itemSelected = new EventEmitter<string>();
  @Output() sidebarToggle = new EventEmitter<void>();

  sidebarItems: SidebarItem[] = [
    {
      id: 'dashboard',
      label: 'Dashboard',
      icon: 'M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2H5a2 2 0 00-2-2z M3 7l9 6 9-6',
    },
    {
      id: 'user-management',
      label: 'User Management',
      icon: 'M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197m13.5-9a2.5 2.5 0 11-5 0 2.5 2.5 0 015 0z',
      // badge: 5,
    },
    {
      id: 'audio-management',
      label: 'Audio Management',
      icon: 'M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M9 21H5a2 2 0 01-2-2V9a2 2 0 012-2h4l7 7-7 7z',
    }
  ];

  // Remove constructor with Router

  // Update active state based on current view
  ngOnInit() {
    this.updateActiveStates();
  }

  ngOnChanges() {
    this.updateActiveStates();
  }

  private updateActiveStates() {
    this.sidebarItems = this.sidebarItems.map(item => ({
      ...item,
      active: item.id === this.currentView
    }));
  }

  selectItem(itemId: string): void {
    this.itemSelected.emit(itemId);

    // Close sidebar on mobile after selection
    if (this.isMobile) {
      this.sidebarToggle.emit();
    }
  }

  closeSidebar(): void {
    if (this.isMobile) {
      this.sidebarToggle.emit();
    }
  }

  trackByFn(index: number, item: SidebarItem): string {
    return item.id;
  }
}