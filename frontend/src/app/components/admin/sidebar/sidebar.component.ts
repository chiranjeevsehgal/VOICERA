import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  AudioLines,
  ClipboardCheck,
  KeyRound,
  LucideAngularModule,
  Users,
  Wallet,
  FileText,
  Upload,
  Activity,
  Scale3D
} from 'lucide-angular';
import { Router } from '@angular/router';
import { ProfileService } from '../../../services/auth/profile.service';
import { AdminAuthService } from '../../../services/admin/admin.auth.service';
import { HotToastService } from '@ngxpert/hot-toast';

export interface SidebarItem {
  id: string;
  label: string;
  icon?: any;
  iconName?: string;
  active?: boolean;
  badge?: number;
}

@Component({
  selector: 'app-sidebar',
  imports: [CommonModule, FormsModule, LucideAngularModule],
  providers: [],
  templateUrl: './sidebar.component.html',
  styles: ``,
})
export class SidebarComponent {
  @Input() isOpen: boolean = false;
  @Input() isMobile: boolean = false;
  @Input() currentView: string = 'user-management';
  @Output() itemSelected = new EventEmitter<string>();
  @Output() sidebarToggle = new EventEmitter<void>();

  constructor(
    private router: Router,
    private toast: HotToastService,
  ) {}

  sidebarItems: SidebarItem[] = [
    {
      id: 'user-management',
      label: 'User Management',
      icon: Users,
    },
    {
      id: 'credit-management',
      label: 'Credits',
      icon: Wallet,
    },
    {
      id: 'audio-management',
      label: 'Audio Management',
      icon: AudioLines,
    },
    {
      id: 'bulk-upload',
      label: 'Bulk Upload',
      icon: Upload,
    },
    {
      id: 'gemini-keys',
      label: 'Gemini Keys',
      icon: KeyRound,
    },
    {
      id: 'logs',
      label: 'Usage Logs',
      icon: ClipboardCheck,
    },
    {
      id: 'application-logs',
      label: 'Application Logs',
      icon: FileText,
    },
    {
      id: 'application-status',
      label: 'Application Status',
      icon: Activity,
    },
    {
      id: 'vector-visualization',
      label: 'Vector Space Visualization',
      icon: Scale3D,
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

  onSignOut(): void {
    localStorage.removeItem('vEra_auth_token');
    localStorage.removeItem('vEra_user_profile');
    localStorage.removeItem('vEra_admin_current-view');

    this.router.navigate(['/login'], {
      queryParams: { loggedOut: 'true' },
    });
  }
}
