import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  AfterViewChecked,
  AfterViewInit,
  CUSTOM_ELEMENTS_SCHEMA,
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  ElementRef,
  NgZone,
  OnDestroy,
  OnInit,
  ViewChild
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { IonIcon } from '@ionic/angular/standalone';
import { addIcons } from 'ionicons';
import {
  addOutline,
  arrowUpOutline,
  checkmarkCircleOutline,
  chevronDownOutline,
  chevronUpOutline,
  personOutline,
  receiptOutline,
  sendOutline,
  shieldCheckmarkOutline,
  sparklesOutline,
  syncOutline,
  thumbsDownOutline,
  thumbsUpOutline,
  trendingUpOutline,
  walletOutline
} from 'ionicons/icons';
import { MarkdownModule } from 'ngx-markdown';

interface Citation {
  claim: string;
  source: string | null;
  verified: boolean;
}

interface Observability {
  token_usage?: Record<string, unknown>;
  node_latencies?: Record<string, number>;
  total_latency_seconds?: number;
  error_log?: unknown[];
  trace_log?: unknown[];
}

interface AgentResponsePayload {
  summary: string;
  confidence: number;
  intent: string;
  data: Record<string, unknown>;
  citations: Citation[];
  warnings: string[];
  tools_used: string[];
  disclaimer: string;
  observability: Observability;
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
  intent?: string;
  toolsUsed?: string[];
  warnings?: string[];
  citations?: Citation[];
  disclaimer?: string;
  latencySeconds?: number;
  detailsExpanded?: boolean;
  /** Set after user submits feedback for this message */
  feedbackRating?: 'thumbs_up' | 'thumbs_down' | null;
  feedbackSubmitting?: boolean;
  /** Show "Thanks for your feedback" briefly after submit */
  feedbackThankYou?: boolean;
}

interface ConversationHistoryResponse {
  thread_id: string;
  messages: { role: 'user' | 'assistant'; content: string }[];
}

interface SuggestedPrompt {
  text: string;
  icon: string;
}

const THREAD_STORAGE_KEY = 'trading_assistant_thread_id';

@Component({
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'page' },
  imports: [
    CommonModule,
    FormsModule,
    IonIcon,
    MarkdownModule,
    MatButtonModule
  ],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  selector: 'gf-trading-agent-page',
  standalone: true,
  styleUrls: ['./trading-agent-page.scss'],
  templateUrl: './trading-agent-page.html'
})
export class GfTradingAgentPageComponent implements OnInit, AfterViewInit, AfterViewChecked, OnDestroy {
  @ViewChild('messagesContainer') private messagesContainer: ElementRef;

  public readonly labelAssistant = $localize`Assistant`;
  public readonly labelUser = $localize`You`;
  public inputMessage = '';
  public isLoading = false;
  public isRestoring = false;
  public messages: ChatMessage[] = [];
  public threadId: string | null = null;

  public readonly suggestedPrompts: SuggestedPrompt[] = [
    {
      text: $localize`Am I too concentrated anywhere?`,
      icon: 'wallet-outline'
    },
    {
      text: $localize`Should I buy more AAPL given my portfolio?`,
      icon: 'shield-checkmark-outline'
    },
    {
      text: $localize`How have my investments performed this year?`,
      icon: 'trending-up-outline'
    },
    {
      text: $localize`What's my tax exposure if I sell?`,
      icon: 'receipt-outline'
    }
  ];

  private shouldScroll = false;

  /** Rotating status text while agent is thinking (updates every 4s) */
  public loadingStatusMessage = '';
  /** Shown after a few seconds to set expectations for long runs */
  public showLoadingHint = false;
  private loadingStatusIndex = 0;
  private loadingStatusTimer: ReturnType<typeof setInterval> | null = null;
  private loadingHintTimer: ReturnType<typeof setTimeout> | null = null;

  private static readonly LOADING_STATUS_MESSAGES = [
    $localize`Analyzing your question...`,
    $localize`Checking portfolio and market data...`,
    $localize`Running compliance and guardrails...`,
    $localize`Preparing your response...`
  ];

  private static readonly TOOL_LABELS: Record<string, string> = {
    get_market_data: 'Market Data',
    detect_regime: 'Regime Detection',
    scan_strategies: 'Strategy Scanner',
    get_portfolio_snapshot: 'Portfolio Snapshot',
    trade_guardrails_check: 'Trade Guardrails',
    portfolio_guardrails_check: 'Portfolio Guardrails',
    get_trade_history: 'Trade History',
    create_activity: 'Activity Logger',
    lookup_symbol: 'Symbol Lookup',
    compliance_check: 'Compliance Check',
    tax_estimate: 'Tax Estimate'
  };

  public constructor(
    private changeDetectorRef: ChangeDetectorRef,
    private elementRef: ElementRef<HTMLElement>,
    private http: HttpClient,
    private ngZone: NgZone
  ) {
    addIcons({
      addOutline,
      arrowUpOutline,
      checkmarkCircleOutline,
      chevronDownOutline,
      chevronUpOutline,
      personOutline,
      receiptOutline,
      sendOutline,
      shieldCheckmarkOutline,
      sparklesOutline,
      syncOutline,
      thumbsDownOutline,
      thumbsUpOutline,
      trendingUpOutline,
      walletOutline
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

  public ngAfterViewInit(): void {
    // Scroll the page so the chat input at the bottom is visible on load (after layout)
    setTimeout(() => this.scrollPageToBottom(), 0);
    setTimeout(() => this.scrollPageToBottom(), 100);
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

  public get sendButtonAriaLabel(): string {
    return this.isLoading ? $localize`Sending...` : $localize`Send`;
  }

  public onSuggestedQuestion(question: string): void {
    this.inputMessage = question;
    this.onSubmit();
  }

  public onNewConversation(): void {
    if (this.isLoading) {
      return;
    }
    this.messages = [];
    this.threadId = crypto.randomUUID();
    localStorage.setItem(THREAD_STORAGE_KEY, this.threadId);
    this.changeDetectorRef.markForCheck();
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
                confidence: r?.confidence,
                intent: r?.intent,
                toolsUsed: r?.tools_used ?? [],
                warnings: r?.warnings ?? [],
                citations: r?.citations ?? [],
                disclaimer: r?.disclaimer,
                latencySeconds: r?.observability?.total_latency_seconds,
                detailsExpanded: false
              }
            ];
            this.isLoading = false;
            this.shouldScroll = true;
            this.stopLoadingIndicators();
            this.changeDetectorRef.markForCheck();
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
          });
        }
      });
  }

  public toggleDetails(index: number): void {
    this.messages = this.messages.map((msg, i) =>
      i === index ? { ...msg, detailsExpanded: !msg.detailsExpanded } : msg
    );
    this.changeDetectorRef.markForCheck();
  }

  public formatToolName(toolName: string): string {
    return (
      GfTradingAgentPageComponent.TOOL_LABELS[toolName] ??
      toolName.replace(/_/g, ' ')
    );
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

  public submitFeedback(index: number, rating: 'thumbs_up' | 'thumbs_down'): void {
    const msg = this.messages[index];
    if (
      !msg ||
      msg.role !== 'assistant' ||
      msg.feedbackRating != null ||
      msg.feedbackSubmitting ||
      !this.threadId
    ) {
      return;
    }
    this.messages = this.messages.map((m, i) =>
      i === index ? { ...m, feedbackSubmitting: true } : m
    );
    this.changeDetectorRef.markForCheck();

    this.http
      .post<{ status: string; feedback_id: string }>(
        '/api/v1/trading-agent/feedback',
        { thread_id: this.threadId, rating }
      )
      .subscribe({
        next: () => {
          this.ngZone.run(() => {
            this.messages = this.messages.map((m, i) =>
              i === index
                ? {
                    ...m,
                    feedbackRating: rating,
                    feedbackSubmitting: false,
                    feedbackThankYou: true
                  }
                : m
            );
            this.changeDetectorRef.markForCheck();
            // Hide "Thanks" after 3s
            setTimeout(() => {
              this.ngZone.run(() => {
                this.messages = this.messages.map((m, i) =>
                  i === index ? { ...m, feedbackThankYou: false } : m
                );
                this.changeDetectorRef.markForCheck();
              });
            }, 3000);
          });
        },
        error: () => {
          this.ngZone.run(() => {
            this.messages = this.messages.map((m, i) =>
              i === index ? { ...m, feedbackSubmitting: false } : m
            );
            this.changeDetectorRef.markForCheck();
          });
        }
      });
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
            setTimeout(() => this.scrollPageToBottom(), 150);
            setTimeout(() => this.scrollPageToBottom(), 500);
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
      const el = this.messagesContainer?.nativeElement;
      if (el) {
        el.scrollTop = el.scrollHeight;
      }
    } catch {
      // ignore
    }
  }

  /** Scroll the page host to bottom so the chat input is in view when opening the page */
  private scrollPageToBottom(): void {
    try {
      const host = this.elementRef?.nativeElement;
      if (host && typeof host.scrollTop !== 'undefined') {
        host.scrollTop = host.scrollHeight;
      }
      // Also scroll window in case the document is the scroll container (e.g. when page content flows)
      if (typeof window !== 'undefined' && window.scrollTo) {
        window.scrollTo(0, document.body.scrollHeight);
      }
    } catch {
      // ignore
    }
  }

  private startLoadingIndicators(): void {
    this.loadingStatusIndex = 0;
    this.loadingStatusMessage =
      GfTradingAgentPageComponent.LOADING_STATUS_MESSAGES[0];
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
          GfTradingAgentPageComponent.LOADING_STATUS_MESSAGES.length;
        this.loadingStatusMessage =
          GfTradingAgentPageComponent.LOADING_STATUS_MESSAGES[
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
