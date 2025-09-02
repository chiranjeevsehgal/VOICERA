import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

interface User {
  id: string;
  name: string;
  email: string;
  role: 'admin' | 'user' | 'moderator';
  status: 'active' | 'inactive' | 'pending';
  lastLogin: Date;
  audioUploads: number;
  searches: number;
}

@Component({
  selector: 'app-user-management',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './user-management.component.html',
  styles: ``,
})
export class UserManagementComponent implements OnInit {
  users: User[] = [
    {
      id: '1',
      name: 'John Doe',
      email: 'john.doe@example.com',
      role: 'admin',
      status: 'active',
      lastLogin: new Date(Date.now() - 2 * 60 * 60 * 1000),
      audioUploads: 45,
      searches: 234,
    },
    {
      id: '2',
      name: 'Jane Smith',
      email: 'jane.smith@company.com',
      role: 'user',
      status: 'active',
      lastLogin: new Date(Date.now() - 1 * 24 * 60 * 60 * 1000),
      audioUploads: 12,
      searches: 89,
    },
    {
      id: '3',
      name: 'Mike Johnson',
      email: 'mike.j@domain.com',
      role: 'moderator',
      status: 'inactive',
      lastLogin: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000),
      audioUploads: 28,
      searches: 156,
    },
    {
      id: '4',
      name: 'Sarah Wilson',
      email: 'sarah.w@test.com',
      role: 'user',
      status: 'pending',
      lastLogin: new Date(Date.now() - 30 * 60 * 1000),
      audioUploads: 3,
      searches: 15,
    },
  ];

  filteredUsers: User[] = [];
  searchQuery: string = '';
  selectedRole: string = 'all';
  selectedStatus: string = 'all';
  showAddUserModal: boolean = false;

  newUser = {
    name: '',
    email: '',
    role: 'user' as 'admin' | 'user' | 'moderator',
  };

  ngOnInit() {
    this.filteredUsers = [...this.users];
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
      moderator: 'bg-yellow-100 text-yellow-700',
      user: 'bg-blue-100 text-blue-700',
    };
    return colors[role] || colors['user'];
  }

  getStatusColor(status: string): string {
    const colors: Record<string, string> = {
      active: 'bg-green-100 text-green-700',
      inactive: 'bg-gray-100 text-gray-700',
      pending: 'bg-orange-100 text-orange-700',
    };
    return colors[status] || colors['pending'];
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

  addUser() {
    const user: User = {
      id: (this.users.length + 1).toString(),
      name: this.newUser.name,
      email: this.newUser.email,
      role: this.newUser.role,
      status: 'pending',
      lastLogin: new Date(),
      audioUploads: 0,
      searches: 0,
    };

    this.users.push(user);
    this.filterUsers();
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
  }

  deleteUser(user: User) {
    if (confirm(`Are you sure you want to delete ${user.name}?`)) {
      this.users = this.users.filter((u) => u.id !== user.id);
      this.filterUsers();
    }
  }

  toggleUserStatus(user: User) {
    user.status = user.status === 'active' ? 'inactive' : 'active';
    this.filterUsers();
  }

  trackUserById(index: number, user: User): string {
    return user.id;
  }
}
