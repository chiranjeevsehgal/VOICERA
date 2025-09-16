import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { FooterComponent } from './components/footer/footer.component';
import { IpPingService } from './services/ip-ping.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, FooterComponent],
  templateUrl: './app.component.html',
  styles: [],
})
export class AppComponent {
  title = 'voicera';

  constructor(_ipPing: IpPingService) {
    // Injecting the service ensures it initializes and subscribes to router events
  }
}
