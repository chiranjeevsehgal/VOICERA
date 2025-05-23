import { Component } from '@angular/core';
import { ForgotPasswordEmailComponent } from '../../components/forgot-password/forgot-password-email/forgot-password-email.component';
import { ForgotPasswordOtpComponent } from '../../components/forgot-password/forgot-password-otp/forgot-password-otp.component';
import { ForgotPasswordResetComponent } from '../../components/forgot-password/forgot-password-reset/forgot-password-reset.component';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { Router } from '@angular/router';

@Component({
  selector: 'app-forgot-password-page',
  imports: [
    Toast,
    ForgotPasswordEmailComponent,
    ForgotPasswordOtpComponent,
    ForgotPasswordResetComponent
  ],
  templateUrl: './forgot-password-page.component.html',
  providers: [
    MessageService
  ]
})
export class ForgotPasswordPageComponent {
  
  emailIsVerified : boolean = false;
  otpIsVerified : boolean = false;
  passwordIsUpdated : boolean = false;

  email : string = "";
  otp : string = "";
  password : string = "";

  constructor(
    private messageService : MessageService,
    private router : Router
  ){

  }

  handleEmailVerified(isVerified: boolean){
    this.emailIsVerified = isVerified;
    if(isVerified){
      // console.log("varified Set to true");
      this.messageService.add({ severity: 'success', summary: 'Verified', detail: "Email Verified Successfully", life: 3000 });
    } else{
      // console.log("varified Set to false");
      this.messageService.add({ severity: 'error', summary: 'Invalid', detail: "Invalid Email", life: 3000 });
    }
  }
  
  handleEmailEmit(email : string){
    this.email = email;
    // console.log("email : ", this.email);
  }

  handleOtpVerified(isVerified : boolean){
    this.otpIsVerified = isVerified;
    if(isVerified){
      // console.log("varified Set to true");
      this.messageService.add({ severity: 'success', summary: 'Verified', detail: "Otp Verified Successfully", life: 3000 });
    } else{
      // console.log("varified Set to false");
      this.messageService.add({ severity: 'error', summary: 'InValid', detail: "Invalid Otp", life: 3000 });
    }
  }

  handleOtpEmit(otp : string){
    this.otp = otp;
    // console.log("email : ", this.email);
  }

  handlePasswordUpdated(isUpdated : boolean){
    this.passwordIsUpdated = isUpdated;

    if(isUpdated){
      this.messageService.add({ severity: 'success', summary: 'Password Updated', detail: "Your Password is updated successfully", life: 3000 });

      setTimeout(() => {
        this.router.navigate(['/login']);
      }, 2000);

    } else {
      this.messageService.add({ severity: 'error', summary: 'Error', detail: "Something went wrong !!", life: 3000 });
    }
  }

}
