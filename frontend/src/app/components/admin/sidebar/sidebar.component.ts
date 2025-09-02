import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AudioLines, Home, LucideAngularModule, Users } from 'lucide-angular';

export interface SidebarItem {
  id: string;
  label: string;
  icon: any;
  active?: boolean;
  badge?: number;
}

@Component({
  selector: 'app-sidebar',
  imports: [CommonModule, FormsModule, LucideAngularModule],
  templateUrl: './sidebar.component.html',
  styles: ``,
})
export class SidebarComponent {
  @Input() isOpen: boolean = false;
  @Input() isMobile: boolean = false;
  @Input() currentView: string = 'dashboard';
  @Output() itemSelected = new EventEmitter<string>();
  @Output() sidebarToggle = new EventEmitter<void>();

  sidebarItems: SidebarItem[] = [
    {
      id: 'dashboard',
      label: 'Dashboard',
      icon: Home,
    },
    {
      id: 'user-management',
      label: 'User Management',
      icon: Users,
    },
    {
      id: 'audio-management',
      label: 'Audio Management',
      icon: AudioLines,
    },
  ];

  ngOnInit() {
    this.updateActiveStates();
  }

  ngOnChanges() {
    this.updateActiveStates();
  }

  private updateActiveStates() {
    this.sidebarItems = this.sidebarItems.map((item) => ({
      ...item,
      active: item.id === this.currentView,
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
