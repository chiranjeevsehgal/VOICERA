import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClientModule } from '@angular/common/http';
import { User, UserService } from '../../../services/admin/user.service';

@Component({
  selector: 'app-user-management',
  standalone: true,
  imports: [CommonModule, FormsModule, HttpClientModule],
  templateUrl: './user-management.component.html',
  styles: ``,
  providers: [UserService],
})
export class UserManagementComponent implements OnInit {
  users: User[] = [];
  filteredUsers: User[] = [];
  searchQuery: string = '';
  selectedRole: string = 'all';
  selectedStatus: string = 'all';
  showAddUserModal: boolean = false;
  loading: boolean = false;
  error: string = '';
  totalCount: number = 0;
  updatingUsers: Set<string> = new Set(); 
  
  newUser = {
    name: '',
    email: '',
    role: 'user' as 'admin' | 'user',
  };

  constructor(private userService: UserService) {}

  ngOnInit() {
    this.loadUsers();
  }

  loadUsers() {
    this.loading = true;
    this.error = '';

    this.userService.getUsers().subscribe({
      next: (response) => {
        this.totalCount = response.total_count;
        this.users = response.users.map((apiUser) =>
          this.userService.transformApiUser(apiUser)
        );
        this.filteredUsers = [...this.users];
        this.loading = false;
      },
      error: (error) => {
        console.error('Error loading users:', error);
        this.error = 'Failed to load users. Please try again.';
        this.loading = false;

        // Fallback to empty array or show error message
        this.users = [];
        this.filteredUsers = [];
      },
    });
  }

  filterUsers() {
    this.filteredUsers = this.users.filter((user) => {
      const matchesSearch =
        user.name.toLowerCase().includes(this.searchQuery.toLowerCase()) ||
        user.email.toLowerCase().includes(this.searchQuery.toLowerCase());
      const matchesRole =
        this.selectedRole === 'all' || user.role === this.selectedRole;
      const matchesStatus =
        this.selectedStatus === 'all' || user.status === this.selectedStatus;

      return matchesSearch && matchesRole && matchesStatus;
    });
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
      (now.getTime() - date.getTime()) / (1000 * 60 * 60)
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

  addUser() {
    // This would need an API endpoint to create users
    console.log('Add user functionality needs API endpoint');
    this.closeAddUserModal();
  }

  openAddUserModal() {
    this.showAddUserModal = true;
  }

  closeAddUserModal() {
    this.showAddUserModal = false;
    this.newUser = { name: '', email: '', role: 'user' };
  }

  editUser(user: User) {
    console.log('Edit user:', user);
    // Implement edit functionality
  }

  deleteUser(user: User) {
    if (confirm(`Are you sure you want to delete ${user.name}?`)) {
      // This would need an API endpoint to delete users
      console.log('Delete user functionality needs API endpoint');
    }
  }

  toggleUserStatus(user: User) {
    // Prevent multiple simultaneous updates for the same user
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
            (u) => u.id === user.id
          );
          if (filteredIndex !== -1) {
            this.filteredUsers[filteredIndex] = updatedUser;
          }
        }

        this.updatingUsers.delete(user.id);
        console.log(`User ${user.name} status updated to ${newStatus}`);
      },
      error: (error) => {
        console.error('Error updating user status:', error);

        // Revert the optimistic update on error
        user.status = originalStatus;

        // Update filtered users to reflect the revert
        const filteredIndex = this.filteredUsers.findIndex(
          (u) => u.id === user.id
        );
        if (filteredIndex !== -1) {
          this.filteredUsers[filteredIndex].status = originalStatus;
        }

        this.updatingUsers.delete(user.id);

        // Show error message to user
        this.error = `Failed to update ${user.name}'s status. Please try again.`;

        // Clear error message after 5 seconds
        setTimeout(() => {
          this.error = '';
        }, 5000);
      },
    });
  }

  isUserBeingUpdated(userId: string): boolean {
    return this.updatingUsers.has(userId);
  }

  refreshUsers() {
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
}
