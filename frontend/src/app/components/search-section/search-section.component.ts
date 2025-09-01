import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Output, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-search-section-title',
  imports: [CommonModule, FormsModule],
  templateUrl: './search-section.component.html',
  styles: ``,
})
export class SerachSectionComponent implements OnInit {
  searchQuery: string = '';
  @Output() searchChange = new EventEmitter<string>();
  @Output() searchSubmit = new EventEmitter<string>();

  ngOnInit(): void {
    // Emit default query so consumers can perform initial search with defaults
    this.searchChange.emit(this.searchQuery);
  }

  onSearchInput(): void {
    this.searchChange.emit(this.searchQuery);
  }

  onSearchClear(): void {
    this.searchQuery = '';
    this.searchChange.emit(this.searchQuery);
  }

  onSubmit(): void {
    this.searchSubmit.emit(this.searchQuery);
  }
}
