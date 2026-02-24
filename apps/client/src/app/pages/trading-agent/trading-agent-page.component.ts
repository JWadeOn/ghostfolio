import { ChangeDetectionStrategy, ChangeDetectorRef, Component, NgZone } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  error?: boolean;
}

interface ChatApiResponse {
  response: {
    summary?: string;
    confidence?: number;
    warnings?: string[];
    disclaimer?: string;
  };
  thread_id: string;
}

@Component({
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'page' },
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressSpinnerModule
  ],
  selector: 'gf-trading-agent-page',
  standalone: true,
  styleUrls: ['./trading-agent-page.scss'],
  templateUrl: './trading-agent-page.html'
})
export class GfTradingAgentPageComponent {
  public readonly labelAssistant = $localize`Assistant`;
  public readonly labelUser = $localize`You`;
  public inputMessage = '';
  public isLoading = false;
  public messages: ChatMessage[] = [];
  public threadId: string | null = null;

  public constructor(
    private changeDetectorRef: ChangeDetectorRef,
    private http: HttpClient,
    private ngZone: NgZone
  ) {}

  public onSubmit() {
    const text = this.inputMessage?.trim();
    if (!text || this.isLoading) {
      return;
    }
    this.inputMessage = '';
    this.messages = [...this.messages, { role: 'user', content: text }];
    this.isLoading = true;

    const body: { message: string; thread_id?: string } = { message: text };
    if (this.threadId) {
      body.thread_id = this.threadId;
    }

    this.http
      .post<ChatApiResponse>('/api/v1/trading-agent/chat', body)
      .subscribe({
        next: (res) => {
          this.ngZone.run(() => {
            this.threadId = res.thread_id ?? this.threadId;
            const summary =
              (res.response && typeof res.response.summary === 'string')
                ? res.response.summary
                : $localize`No response generated.`;
            this.messages = [
              ...this.messages,
              { role: 'assistant', content: summary }
            ];
            this.isLoading = false;
            this.changeDetectorRef.markForCheck();
          });
        },
        error: (err) => {
          this.ngZone.run(() => {
            const message =
              err?.error?.error ?? $localize`Trading agent is unavailable.`;
            this.messages = [
              ...this.messages,
              { role: 'assistant', content: message, error: true }
            ];
            this.isLoading = false;
            this.changeDetectorRef.markForCheck();
          });
        }
      });
  }
}
