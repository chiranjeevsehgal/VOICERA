import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-search-section-title',
  imports: [CommonModule, FormsModule],
  templateUrl: './search-section.component.html',
  styles: ``,
})
export class SerachSectionComponent {
  searchQuery: string = '';
  @Output() searchChange = new EventEmitter<string>();

  onSearchInput(): void {
    this.searchChange.emit(this.searchQuery);
  }

  onSearchClear(): void {
    this.searchQuery = '';
    this.searchChange.emit(this.searchQuery);
  }
}
