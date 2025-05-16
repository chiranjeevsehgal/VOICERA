import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms'; 

@Component({
  selector: 'app-login-form',
  standalone: false,
  templateUrl: './login-form.component.html',
  styles: ``,
})
export class LoginFormComponent {
  loginForm: FormGroup;
  isLoading : boolean = true;

  constructor(private fb: FormBuilder) {
    this.loginForm = this.fb.group({
      email: ['', [Validators.required, Validators.email]],
      password: ['', Validators.required]
    });
  }

  onSubmit() {
    if (this.loginForm.valid) {
      console.log('Form submitted', this.loginForm.value);
    }
  }
}
