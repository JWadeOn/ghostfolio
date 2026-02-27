import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  AfterViewChecked,
  CUSTOM_ELEMENTS_SCHEMA,
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  ElementRef,
  NgZone,
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
  sendOutline,
  shieldCheckmarkOutline,
  sparklesOutline,
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
export class GfTradingAgentPageComponent implements OnInit, AfterViewChecked {
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
      text: $localize`What does my portfolio look like?`,
      icon: 'wallet-outline'
    },
    {
      text: $localize`Can I buy $10k of TSLA?`,
      icon: 'shield-checkmark-outline'
    },
    {
      text: $localize`What's the current market regime?`,
      icon: 'trending-up-outline'
    },
    {
      text: $localize`Scan for trading opportunities`,
      icon: 'checkmark-circle-outline'
    }
  ];

  private shouldScroll = false;

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
      sendOutline,
      shieldCheckmarkOutline,
      sparklesOutline,
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

  public get hasConversationStarted(): boolean {
    return this.messages.length > 0;
  }

  public get inputPlaceholder(): string {
    return this.hasConversationStarted
      ? $localize`Follow up...`
      : $localize`Ask anything about your portfolio...`;
  }

  public startNewConversation(): void {
    this.threadId = crypto.randomUUID();
    localStorage.setItem(THREAD_STORAGE_KEY, this.threadId);
    this.messages = [];
    this.changeDetectorRef.markForCheck();
  }

  public onSuggestedQuestion(question: string): void {
    this.inputMessage = question;
    this.onSubmit();
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
              this.shouldScroll = true;
            }
            this.isRestoring = false;
            this.changeDetectorRef.markForCheck();
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
}
