import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  AfterViewChecked,
  CUSTOM_ELEMENTS_SCHEMA,
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  ElementRef,
  EventEmitter,
  NgZone,
  OnDestroy,
  OnInit,
  Output,
  ViewChild
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { internalRoutes } from '@ghostfolio/common/routes/routes';
import { IonIcon } from '@ionic/angular/standalone';
import { addIcons } from 'ionicons';
import {
  arrowUpOutline,
  closeOutline,
  expandOutline,
  sendOutline,
  sparklesOutline,
  syncOutline
} from 'ionicons/icons';
import { MarkdownModule } from 'ngx-markdown';

interface AgentResponsePayload {
  summary: string;
  confidence: number;
  intent: string;
  data: Record<string, unknown>;
  citations: unknown[];
  warnings: string[];
  tools_used: string[];
  disclaimer: string;
  observability: {
    total_latency_seconds?: number;
  };
}

interface ChatApiResponse {
  response: AgentResponsePayload;
  thread_id: string;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  error?: boolean;
  confidence?: number;
}

interface ConversationHistoryResponse {
  thread_id: string;
  messages: { role: 'user' | 'assistant'; content: string }[];
}

const THREAD_STORAGE_KEY = 'trading_assistant_thread_id';

@Component({
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, FormsModule, IonIcon, MarkdownModule],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  selector: 'gf-trading-agent-widget',
  standalone: true,
  styleUrls: ['./trading-agent-widget.scss'],
  templateUrl: './trading-agent-widget.html'
})
export class GfTradingAgentWidgetComponent
  implements OnInit, AfterViewChecked, OnDestroy
{
  @Output() closed = new EventEmitter<void>();
  @ViewChild('widgetMessages') private messagesEl: ElementRef;

  public inputMessage = '';
  public isLoading = false;
  public isRestoring = false;
  public messages: ChatMessage[] = [];
  public threadId: string | null = null;

  public loadingStatusMessage = '';
  public showLoadingHint = false;
  private loadingStatusIndex = 0;
  private loadingStatusTimer: ReturnType<typeof setInterval> | null = null;
  private loadingHintTimer: ReturnType<typeof setTimeout> | null = null;
  private shouldScroll = false;

  private static readonly LOADING_STATUS_MESSAGES = [
    $localize`Analyzing your question...`,
    $localize`Checking portfolio and market data...`,
    $localize`Running compliance and guardrails...`,
    $localize`Preparing your response...`
  ];

  public constructor(
    private changeDetectorRef: ChangeDetectorRef,
    private http: HttpClient,
    private ngZone: NgZone,
    private router: Router
  ) {
    addIcons({
      arrowUpOutline,
      closeOutline,
      expandOutline,
      sendOutline,
      sparklesOutline,
      syncOutline
    });
  }

  public ngOnInit(): void {
    const stored = localStorage.getItem(THREAD_STORAGE_KEY);
    if (stored) {
      this.threadId = stored;
      this.restoreHistory(stored);
    } else {
      this.threadId = crypto.randomUUID();
      localStorage.setItem(THREAD_STORAGE_KEY, this.threadId);
    }
  }

  public ngAfterViewChecked(): void {
    if (this.shouldScroll) {
      this.scrollToBottom();
      this.shouldScroll = false;
    }
  }

  public ngOnDestroy(): void {
    this.stopLoadingIndicators();
  }

  public get hasConversationStarted(): boolean {
    return this.messages.length > 0;
  }

  public get inputPlaceholder(): string {
    return this.hasConversationStarted
      ? $localize`Follow up...`
      : $localize`Ask anything about your portfolio...`;
  }

  public onClose(): void {
    this.closed.emit();
  }

  public onOpenFullPage(): void {
    this.closed.emit();
    this.router.navigate(internalRoutes.tradingAgent.routerLink);
  }

  public onSubmit(): void {
    const text = this.inputMessage?.trim();
    if (!text || this.isLoading) {
      return;
    }
    this.inputMessage = '';
    this.messages = [
      ...this.messages,
      { role: 'user', content: text, timestamp: new Date() }
    ];
    this.isLoading = true;
    this.shouldScroll = true;
    this.startLoadingIndicators();

    const body = { message: text, thread_id: this.threadId };

    this.http
      .post<ChatApiResponse>('/api/v1/trading-agent/chat', body)
      .subscribe({
        next: (res) => {
          this.ngZone.run(() => {
            this.threadId = res.thread_id ?? this.threadId;
            localStorage.setItem(THREAD_STORAGE_KEY, this.threadId);
            const r = res.response;
            const summary =
              r && typeof r.summary === 'string'
                ? r.summary
                : $localize`No response generated.`;
            this.messages = [
              ...this.messages,
              {
                role: 'assistant',
                content: summary,
                timestamp: new Date(),
                confidence: r?.confidence
              }
            ];
            this.isLoading = false;
            this.shouldScroll = true;
            this.stopLoadingIndicators();
            this.changeDetectorRef.markForCheck();
            // Delayed scrolls to catch async markdown rendering
            setTimeout(() => this.scrollToBottom(), 50);
            setTimeout(() => this.scrollToBottom(), 200);
            setTimeout(() => this.scrollToBottom(), 500);
          });
        },
        error: (err) => {
          this.ngZone.run(() => {
            const message =
              err?.error?.error ?? $localize`Trading agent is unavailable.`;
            this.messages = [
              ...this.messages,
              {
                role: 'assistant',
                content: message,
                timestamp: new Date(),
                error: true
              }
            ];
            this.isLoading = false;
            this.shouldScroll = true;
            this.stopLoadingIndicators();
            this.changeDetectorRef.markForCheck();
            setTimeout(() => this.scrollToBottom(), 50);
          });
        }
      });
  }

  public getConfidenceLevel(confidence: number): {
    label: string;
    cssClass: string;
  } {
    if (confidence >= 80) {
      return { label: $localize`High`, cssClass: 'confidence-high' };
    }
    if (confidence >= 50) {
      return { label: $localize`Medium`, cssClass: 'confidence-medium' };
    }
    return { label: $localize`Low`, cssClass: 'confidence-low' };
  }

  private restoreHistory(threadId: string): void {
    this.isRestoring = true;
    this.changeDetectorRef.markForCheck();

    this.http
      .get<ConversationHistoryResponse>(
        `/api/v1/trading-agent/conversation/${threadId}`
      )
      .subscribe({
        next: (res) => {
          this.ngZone.run(() => {
            if (res.messages?.length) {
              this.messages = res.messages.map((m) => ({
                role: m.role,
                content: m.content,
                timestamp: new Date()
              }));
            }
            this.isRestoring = false;
            this.shouldScroll = true;
            this.changeDetectorRef.markForCheck();
            setTimeout(() => this.scrollToBottom(), 100);
            setTimeout(() => this.scrollToBottom(), 400);
          });
        },
        error: () => {
          this.ngZone.run(() => {
            this.isRestoring = false;
            this.changeDetectorRef.markForCheck();
          });
        }
      });
  }

  private scrollToBottom(): void {
    try {
      const el = this.messagesEl?.nativeElement;
      if (el) {
        el.scrollTop = el.scrollHeight;
      }
    } catch {
      // ignore
    }
  }

  private startLoadingIndicators(): void {
    this.loadingStatusIndex = 0;
    this.loadingStatusMessage =
      GfTradingAgentWidgetComponent.LOADING_STATUS_MESSAGES[0];
    this.showLoadingHint = false;
    this.loadingHintTimer = setTimeout(() => {
      this.loadingHintTimer = null;
      this.ngZone.run(() => {
        this.showLoadingHint = true;
        this.changeDetectorRef.markForCheck();
      });
    }, 5000);
    this.loadingStatusTimer = setInterval(() => {
      this.ngZone.run(() => {
        this.loadingStatusIndex =
          (this.loadingStatusIndex + 1) %
          GfTradingAgentWidgetComponent.LOADING_STATUS_MESSAGES.length;
        this.loadingStatusMessage =
          GfTradingAgentWidgetComponent.LOADING_STATUS_MESSAGES[
            this.loadingStatusIndex
          ];
        this.changeDetectorRef.markForCheck();
      });
    }, 4000);
  }

  private stopLoadingIndicators(): void {
    if (this.loadingHintTimer != null) {
      clearTimeout(this.loadingHintTimer);
      this.loadingHintTimer = null;
    }
    if (this.loadingStatusTimer != null) {
      clearInterval(this.loadingStatusTimer);
      this.loadingStatusTimer = null;
    }
    this.showLoadingHint = false;
    this.loadingStatusMessage = '';
  }
}
