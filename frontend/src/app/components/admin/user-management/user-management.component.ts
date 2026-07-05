import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { User, UserService } from '../../../services/admin/user.service';
import {
  LucideDynamicIcon,
  LucideCheck as Check,
  LucideX as X,
  LucideUsers as Users,
} from '@lucide/angular';
import {
  getCurrentUserRole,
  shouldUseMockData,
} from '../../../utils/role.utils';
import * as mockUserData from '../../../utils/mockData/mockUsers.json';
import { HotToastService } from '@ngxpert/hot-toast';
import { Subject, Subscription } from 'rxjs';
import { debounceTime, distinctUntilChanged } from 'rxjs/operators';

@Component({
  selector: 'app-user-management',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    LucideDynamicIcon,
  ],
  providers: [UserService],
  templateUrl: './user-management.component.html',
  styles: ``,
})
export class UserManagementComponent implements OnInit, OnDestroy {
  users: User[] = [];
  readonly Check = Check;
  readonly X = X;
  readonly Users = Users;
  filteredUsers: User[] = [];
  searchQuery: string = '';
  selectedRole: string = 'all';
  selectedStatus: string = 'all';
  showAddUserModal: boolean = false;
  loading: boolean = false;
  refreshing: boolean = false;
  totalCount: number = 0;
  updatingUsers: Set<string> = new Set();
  userToDelete: User | null = null;
  deleteMode: 'deactivate' | 'delete' = 'delete';
  showDeleteModal: boolean = false;
  deletingUserId: string = '';

  // Pagination and sorting
  page: number = 1;
  limit: number = 10;
  sortBy: string = 'created_at';
  sortOrder: 1 | -1 = -1;

  // Debounced search
  private searchInput$ = new Subject<string>();
  private searchSub?: Subscription;

  newUser = {
    name: '',
    email: '',
    role: 'user' as 'admin' | 'user',
  };

  constructor(
    private userService: UserService,
    private toast: HotToastService,
  ) {}

  ngOnInit() {
    // Debounce search input
    this.searchSub = this.searchInput$
      .pipe(debounceTime(400), distinctUntilChanged())
      .subscribe(() => {
        this.page = 1;
        this.loadUsers();
      });

    this.loadUsers();
  }

  ngOnDestroy(): void {
    this.searchSub?.unsubscribe();
  }

  get totalPages(): number {
    return Math.max(1, Math.ceil(this.totalCount / this.limit));
  }

  loadUsers() {
    this.loading = true;

    // Check if we should use mock data
    if (shouldUseMockData()) {
      // Mock data response with proper typing
      const mockResponse = mockUserData as any;

      // Transform all users first
      const allUsers: User[] = mockResponse.users.map((apiUser: any) =>
        this.userService.transformApiUser(apiUser),
      );

      // Apply filters and search on client for mock mode
      const roleFilter = this.selectedRole !== 'all' ? this.selectedRole : null;
      const statusFilter =
        this.selectedStatus !== 'all' ? this.selectedStatus : null;
      const search = this.searchQuery.trim().toLowerCase();

      const filtered = allUsers.filter((u) => {
        const matchesRole = roleFilter ? u.role === roleFilter : true;
        const matchesStatus = statusFilter ? u.status === statusFilter : true;
        const matchesSearch = search
          ? u.name.toLowerCase().includes(search) ||
            u.email.toLowerCase().includes(search)
          : true;
        return matchesRole && matchesStatus && matchesSearch;
      });

      // Sort
      const sorted = [...filtered].sort((a, b) => {
        const aVal: any = (a as any)[
          this.sortBy === 'created_at' ? 'createdAt' : this.sortBy
        ];
        const bVal: any = (b as any)[
          this.sortBy === 'created_at' ? 'createdAt' : this.sortBy
        ];
        if (aVal < bVal) return this.sortOrder === 1 ? -1 : 1;
        if (aVal > bVal) return this.sortOrder === 1 ? 1 : -1;
        return 0;
      });

      this.totalCount = sorted.length;

      // Paginate
      const start = (this.page - 1) * this.limit;
      const end = start + this.limit;
      const pageSlice = sorted.slice(start, end);

      this.users = pageSlice;
      this.filteredUsers = [...this.users];
      this.loading = false;
      this.refreshing = false;

      return;
    }

    // Normal API call flow
    this.userService
      .getUsers({
        page: this.page,
        limit: this.limit,
        sort_by: this.sortBy,
        sort_order: this.sortOrder,
        role: this.selectedRole !== 'all' ? this.selectedRole : undefined,
        status: this.selectedStatus !== 'all' ? this.selectedStatus : undefined,
        search: this.searchQuery?.trim() ? this.searchQuery.trim() : undefined,
      })
      .subscribe({
      next: (response) => {
        this.totalCount = response.total_count;
        this.users = response.users.map((apiUser) =>
          this.userService.transformApiUser(apiUser),
        );
        this.filteredUsers = [...this.users];
        this.loading = false;
        this.refreshing = false;
      },
      error: (error) => {
        console.error('Error loading users:', error);
        this.toast.error("Failed to load users. Please try again.");
        this.loading = false;


        // Fallback to empty array 
        this.users = [];
        this.filteredUsers = [];
      },
    });
  }

  onSearchInput(value: string) {
    this.searchQuery = value;
    this.searchInput$.next(this.searchQuery);
  }

  onFilterChange() {
    this.page = 1;
    this.loadUsers();
  }

  onLimitChange(newLimit: number) {
    this.limit = newLimit;
    this.page = 1;
    this.loadUsers();
  }

  nextPage() {
    if (this.page < this.totalPages) {
      this.page += 1;
      this.loadUsers();
    }
  }

  prevPage() {
    if (this.page > 1) {
      this.page -= 1;
      this.loadUsers();
    }
  }

  goToPage(page: number) {
    if (page >= 1 && page <= this.totalPages) {
      this.page = page;
      this.loadUsers();
    }
  }

  displayStartIndex(): number {
    if (this.totalCount === 0) return 0;
    return (this.page - 1) * this.limit + 1;
    }

  displayEndIndex(): number {
    return Math.min(this.page * this.limit, this.totalCount);
  }

  getRoleColor(role: string): string {
    const colors: Record<string, string> = {
      admin: 'bg-red-100 text-red-700',
      user: 'bg-blue-100 text-blue-700',
    };
    return colors[role] || colors['user'];
  }

  getStatusColor(status: string): string {
    const colors: Record<string, string> = {
      active: 'bg-green-100 text-green-700',
      inactive: 'bg-gray-100 text-gray-700',
    };
    return colors[status];
  }

  formatLastLogin(date: Date): string {
    const now = new Date();
    const diffInHours = Math.floor(
      (now.getTime() - date.getTime()) / (1000 * 60 * 60),
    );

    if (diffInHours < 1) return 'Just now';
    if (diffInHours < 24) return `${diffInHours}h ago`;

    const diffInDays = Math.floor(diffInHours / 24);
    if (diffInDays < 30) return `${diffInDays}d ago`;

    const diffInMonths = Math.floor(diffInDays / 30);
    return `${diffInMonths}mo ago`;
  }

  formatCreatedAt(date: Date): string {
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  }

  toggleUserStatus(user: User) {
    // Prevent multiple simultaneous updates for the same user
    if (shouldUseMockData()) {
      this.toast.info(
        'User status modifications are disabled in the guest environment.',
      );
      return;
    }
    if (this.updatingUsers.has(user.id)) {
      return;
    }

    const newStatus: 'active' | 'inactive' =
      user.status === 'active' ? 'inactive' : 'active';
    const originalStatus = user.status;

    // Add user to updating set
    this.updatingUsers.add(user.id);

    // Optimistically update the UI
    user.status = newStatus;

    this.userService.updateUserStatus(user.id, newStatus).subscribe({
      next: (updatedApiUser) => {
        // Update the user with the response from the API
        const updatedUser = this.userService.transformApiUser(updatedApiUser);
        const userIndex = this.users.findIndex((u) => u.id === user.id);

        if (userIndex !== -1) {
          this.users[userIndex] = updatedUser;
          // Update filtered users as well
          const filteredIndex = this.filteredUsers.findIndex(
            (u) => u.id === user.id,
          );
          if (filteredIndex !== -1) {
            this.filteredUsers[filteredIndex] = updatedUser;
          }
        }

        this.updatingUsers.delete(user.id);
        this.toast.success(`User ${user.name} has been ${
            newStatus === 'active' ? 'activated' : 'deactivated'
          } successfully.`);
      },
      error: (error) => {
        console.error('Error updating user status:', error);

        // Revert the optimistic update on error
        user.status = originalStatus;

        // Update filtered users to reflect the revert
        const filteredIndex = this.filteredUsers.findIndex(
          (u) => u.id === user.id,
        );
        if (filteredIndex !== -1) {
          this.filteredUsers[filteredIndex].status = originalStatus;
        }

        this.updatingUsers.delete(user.id);

        this.toast.error(`Failed to update ${user.name}'s status. Please try again.`);

      },
    });
  }

  isUserBeingUpdated(userId: string): boolean {
    return this.updatingUsers.has(userId);
  }

  refreshUsers() {
    this.refreshing = true;
    this.loadUsers();
  }

  trackUserById(index: number, user: User): string {
    return user.id;
  }

  getUserInitials(name: string): string {
    return name
      .split(' ')
      .map((word) => word.charAt(0))
      .join('')
      .toUpperCase()
      .substring(0, 2);
  }

  openDeleteModal(user: User, mode: 'deactivate' | 'delete' = 'delete') {
    if (shouldUseMockData()) {
      this.toast.info('User deletion is restricted in the guest environment.');
      return;
    }
    this.userToDelete = user;
    this.deleteMode = mode;
    this.showDeleteModal = true;
  }

  closeDeleteModal() {
    this.showDeleteModal = false;
    this.userToDelete = null;
    this.deleteMode = 'delete';
  }

  confirmDeleteUser() {
    if (!this.userToDelete) return;

    this.deletingUserId = this.userToDelete.id;

    this.userService.deleteUser(this.userToDelete.id).subscribe({
      next: () => {
        // Remove user from local arrays
        this.users = this.users.filter((u) => u.id !== this.userToDelete!.id);
        this.filteredUsers = this.filteredUsers.filter(
          (u) => u.id !== this.userToDelete!.id,
        );
        this.totalCount = Math.max(0, this.totalCount - 1);

        // Show success message
        this.toast.success(`User ${
            this.userToDelete!.name
          } has been deleted successfully.`);

        this.closeDeleteModal();
        this.deletingUserId = '';
      },
      error: (error) => {
        console.error('Error deleting user:', error);
        this.toast.error(`Failed to delete user. Please try again.`);
        this.deletingUserId = '';

      },
    });
  }
}
