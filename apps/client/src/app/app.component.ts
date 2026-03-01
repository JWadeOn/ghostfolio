import { getCssVariable } from '@ghostfolio/common/helper';
import { InfoItem, User } from '@ghostfolio/common/interfaces';
import { hasPermission, permissions } from '@ghostfolio/common/permissions';
import { internalRoutes, publicRoutes } from '@ghostfolio/common/routes/routes';
import { ColorScheme } from '@ghostfolio/common/types';
import { NotificationService } from '@ghostfolio/ui/notifications';
import { DataService } from '@ghostfolio/ui/services';

import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  DOCUMENT,
  HostBinding,
  HostListener,
  Inject,
  OnDestroy,
  OnInit
} from '@angular/core';
import { MatDialog } from '@angular/material/dialog';
import { Title } from '@angular/platform-browser';
import {
  ActivatedRoute,
  NavigationEnd,
  PRIMARY_OUTLET,
  Router,
  RouterLink,
  RouterOutlet
} from '@angular/router';
import { IonIcon } from '@ionic/angular/standalone';
import { DataSource } from '@prisma/client';
import { addIcons } from 'ionicons';
import { openOutline } from 'ionicons/icons';
import { DeviceDetectorService } from 'ngx-device-detector';
import { Subject } from 'rxjs';
import { filter, takeUntil } from 'rxjs/operators';

import { GfFooterComponent } from './components/footer/footer.component';
import { GfHeaderComponent } from './components/header/header.component';
import { GfHoldingDetailDialogComponent } from './components/holding-detail-dialog/holding-detail-dialog.component';
import { HoldingDetailDialogParams } from './components/holding-detail-dialog/interfaces/interfaces';
import { ImpersonationStorageService } from './services/impersonation-storage.service';
import { TokenStorageService } from './services/token-storage.service';
import { UserService } from './services/user/user.service';

@Component({
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    GfFooterComponent,
    GfHeaderComponent,
    IonIcon,
    RouterLink,
    RouterOutlet
  ],
  selector: 'gf-root',
  styleUrls: ['./app.component.scss'],
  templateUrl: './app.component.html'
})
export class GfAppComponent implements OnDestroy, OnInit {
  @HostBinding('class.has-info-message') get getHasMessage() {
    return this.hasInfoMessage;
  }

  public canCreateAccount: boolean;
  public currentRoute: string;
  public currentSubRoute: string;
  public deviceType: string;
  public hasImpersonationId: boolean;
  public hasInfoMessage: boolean;
  public hasPermissionToChangeDateRange: boolean;
  public hasPermissionToChangeFilters: boolean;
  public hasPromotion = false;
  public hasTabs = false;
  public info: InfoItem;
  public pageTitle: string;
  public routerLinkRegister = publicRoutes.register.routerLink;
  public showFooter = false;
  public user: User;
  public internalRoutes = internalRoutes;

  /** Draggable widget position (px from left/top). When null, use CSS default (bottom-left). */
  public tradingAgentWidgetPosition: { x: number; y: number } | null = null;
  private readonly TRADING_AGENT_POSITION_KEY = 'gf_trading_agent_widget_position';
  private dragStartX = 0;
  private dragStartY = 0;
  private dragStartLeft = 0;
  private dragStartTop = 0;
  private isDragActive = false;
  private didMoveEnough = false;
  public wasDragging = false;

  private unsubscribeSubject = new Subject<void>();

  public constructor(
    private changeDetectorRef: ChangeDetectorRef,
    private dataService: DataService,
    private deviceService: DeviceDetectorService,
    private dialog: MatDialog,
    @Inject(DOCUMENT) private document: Document,
    private impersonationStorageService: ImpersonationStorageService,
    private notificationService: NotificationService,
    private route: ActivatedRoute,
    private router: Router,
    private title: Title,
    private tokenStorageService: TokenStorageService,
    private userService: UserService
  ) {
    this.initializeTheme();
    this.user = undefined;

    this.route.queryParams
      .pipe(takeUntil(this.unsubscribeSubject))
      .subscribe((params) => {
        if (
          params['dataSource'] &&
          params['holdingDetailDialog'] &&
          params['symbol']
        ) {
          this.openHoldingDetailDialog({
            dataSource: params['dataSource'],
            symbol: params['symbol']
          });
        }
      });

    addIcons({ openOutline });
  }

  public get showTradingAgentFab(): boolean {
    return (
      !!this.user &&
      hasPermission(this.user?.permissions, permissions.readAiPrompt) &&
      this.currentRoute !== internalRoutes.tradingAgent.path
    );
  }

  public getTradingAgentWidgetStyle(): Record<string, string> {
    const pos = this.tradingAgentWidgetPosition;
    if (!pos) return {};
    return {
      left: `${pos.x}px`,
      top: `${pos.y}px`,
      bottom: 'auto',
      right: 'auto'
    };
  }

  public onTradingAgentWidgetPointerDown(event: MouseEvent | TouchEvent): void {
    if (!this.showTradingAgentFab) return;
    const isTouch = event instanceof TouchEvent;
    const clientX = isTouch ? (event as TouchEvent).touches[0].clientX : (event as MouseEvent).clientX;
    const clientY = isTouch ? (event as TouchEvent).touches[0].clientY : (event as MouseEvent).clientY;
    if (!isTouch && (event as MouseEvent).button !== 0) return;

    const rect = (event.target as HTMLElement).closest('.trading-agent-float')?.getBoundingClientRect();
    if (!rect) return;

    this.isDragActive = true;
    this.didMoveEnough = false;
    this.dragStartX = clientX;
    this.dragStartY = clientY;
    this.dragStartLeft = this.tradingAgentWidgetPosition
      ? this.tradingAgentWidgetPosition.x
      : Math.round(rect.left);
    this.dragStartTop = this.tradingAgentWidgetPosition
      ? this.tradingAgentWidgetPosition.y
      : Math.round(rect.top);
  }

  @HostListener('document:mousemove', ['$event'])
  onDocumentMouseMove(event: MouseEvent): void {
    if (!this.isDragActive || !this.showTradingAgentFab) return;
    const dx = event.clientX - this.dragStartX;
    const dy = event.clientY - this.dragStartY;
    if (!this.didMoveEnough && (Math.abs(dx) > 5 || Math.abs(dy) > 5)) {
      this.didMoveEnough = true;
    }
    if (this.didMoveEnough) {
      const padding = 16;
      const maxW = this.document.documentElement.clientWidth - 200;
      const maxH = this.document.documentElement.clientHeight - 120;
      const x = Math.max(padding, Math.min(maxW, this.dragStartLeft + dx));
      const y = Math.max(padding, Math.min(maxH, this.dragStartTop + dy));
      this.tradingAgentWidgetPosition = { x, y };
      this.changeDetectorRef.markForCheck();
    }
  }

  @HostListener('document:mouseup')
  onDocumentMouseUp(): void {
    if (!this.isDragActive) return;
    if (this.didMoveEnough) {
      this.wasDragging = true;
      this.saveTradingAgentPosition();
    }
    this.isDragActive = false;
    this.changeDetectorRef.markForCheck();
  }

  @HostListener('document:touchmove', ['$event'])
  onDocumentTouchMove(event: TouchEvent): void {
    if (!this.isDragActive || !this.showTradingAgentFab || !event.touches.length) return;
    const dx = event.touches[0].clientX - this.dragStartX;
    const dy = event.touches[0].clientY - this.dragStartY;
    if (!this.didMoveEnough && (Math.abs(dx) > 5 || Math.abs(dy) > 5)) {
      this.didMoveEnough = true;
    }
    if (this.didMoveEnough) {
      event.preventDefault();
      const padding = 16;
      const maxW = this.document.documentElement.clientWidth - 200;
      const maxH = this.document.documentElement.clientHeight - 120;
      const x = Math.max(padding, Math.min(maxW, this.dragStartLeft + dx));
      const y = Math.max(padding, Math.min(maxH, this.dragStartTop + dy));
      this.tradingAgentWidgetPosition = { x, y };
      this.changeDetectorRef.markForCheck();
    }
  }

  @HostListener('document:touchend')
  onDocumentTouchEnd(): void {
    if (!this.isDragActive) return;
    if (this.didMoveEnough) {
      this.wasDragging = true;
      this.saveTradingAgentPosition();
    }
    this.isDragActive = false;
    this.changeDetectorRef.markForCheck();
  }

  public onTradingAgentFabClick(event: Event): void {
    if (this.wasDragging) {
      event.preventDefault();
      event.stopPropagation();
      this.wasDragging = false;
    }
  }

  private loadTradingAgentPosition(): void {
    try {
      const raw = this.document.defaultView?.localStorage?.getItem(this.TRADING_AGENT_POSITION_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as { x: number; y: number };
        const padding = 16;
        const maxW = this.document.documentElement.clientWidth - 200;
        const maxH = this.document.documentElement.clientHeight - 120;
        this.tradingAgentWidgetPosition = {
          x: Math.max(padding, Math.min(maxW, parsed.x)),
          y: Math.max(padding, Math.min(maxH, parsed.y))
        };
      }
    } catch {
      // ignore
    }
  }

  private saveTradingAgentPosition(): void {
    if (!this.tradingAgentWidgetPosition) return;
    try {
      this.document.defaultView?.localStorage?.setItem(
        this.TRADING_AGENT_POSITION_KEY,
        JSON.stringify(this.tradingAgentWidgetPosition)
      );
    } catch {
      // ignore
    }
  }

  public ngOnInit() {
    this.deviceType = this.deviceService.getDeviceInfo().deviceType;
    this.info = this.dataService.fetchInfo();
    this.updateRouteFromRouter();
    this.loadTradingAgentPosition();

    this.impersonationStorageService
      .onChangeHasImpersonation()
      .pipe(takeUntil(this.unsubscribeSubject))
      .subscribe((impersonationId) => {
        this.hasImpersonationId = !!impersonationId;
      });

    this.router.events
      .pipe(filter((event) => event instanceof NavigationEnd))
      .subscribe(() => {
        this.updateRouteFromRouter();

        if (
          ((this.currentRoute === internalRoutes.home.path &&
            !this.currentSubRoute) ||
            (this.currentRoute === internalRoutes.home.path &&
              this.currentSubRoute ===
                internalRoutes.home.subRoutes.holdings.path) ||
            (this.currentRoute === internalRoutes.portfolio.path &&
              !this.currentSubRoute)) &&
          this.user?.settings?.viewMode !== 'ZEN'
        ) {
          this.hasPermissionToChangeDateRange = true;
        } else {
          this.hasPermissionToChangeDateRange = false;
        }

        if (
          (this.currentRoute === internalRoutes.home.path &&
            this.currentSubRoute ===
              internalRoutes.home.subRoutes.holdings.path) ||
          (this.currentRoute === internalRoutes.portfolio.path &&
            !this.currentSubRoute) ||
          (this.currentRoute === internalRoutes.portfolio.path &&
            this.currentSubRoute ===
              internalRoutes.portfolio.subRoutes.activities.path) ||
          (this.currentRoute === internalRoutes.portfolio.path &&
            this.currentSubRoute ===
              internalRoutes.portfolio.subRoutes.allocations.path) ||
          (this.currentRoute === internalRoutes.zen.path &&
            this.currentSubRoute ===
              internalRoutes.home.subRoutes.holdings.path)
        ) {
          this.hasPermissionToChangeFilters = true;
        } else {
          this.hasPermissionToChangeFilters = false;
        }

        this.hasTabs =
          (this.currentRoute === publicRoutes.about.path ||
            this.currentRoute === publicRoutes.faq.path ||
            this.currentRoute === publicRoutes.resources.path ||
            this.currentRoute === internalRoutes.account.path ||
            this.currentRoute === internalRoutes.adminControl.path ||
            this.currentRoute === internalRoutes.home.path ||
            this.currentRoute === internalRoutes.portfolio.path ||
            this.currentRoute === internalRoutes.zen.path) &&
          this.deviceType !== 'mobile';

        this.showFooter =
          (this.currentRoute === publicRoutes.blog.path ||
            this.currentRoute === publicRoutes.features.path ||
            this.currentRoute === publicRoutes.markets.path ||
            this.currentRoute === publicRoutes.openStartup.path ||
            this.currentRoute === publicRoutes.public.path ||
            this.currentRoute === publicRoutes.pricing.path ||
            this.currentRoute === publicRoutes.register.path ||
            this.currentRoute === publicRoutes.start.path) &&
          this.deviceType !== 'mobile';

        if (this.deviceType === 'mobile') {
          setTimeout(() => {
            const index = this.title.getTitle().indexOf('–');
            const title =
              index === -1
                ? ''
                : this.title.getTitle().substring(0, index).trim();
            this.pageTitle = title.length <= 15 ? title : 'Ghostfolio';

            this.changeDetectorRef.markForCheck();
          });
        }

        this.changeDetectorRef.markForCheck();
      });

    this.userService.stateChanged
      .pipe(takeUntil(this.unsubscribeSubject))
      .subscribe((state) => {
        this.user = state.user;

        this.canCreateAccount = hasPermission(
          this.user?.permissions,
          permissions.createUserAccount
        );

        this.hasInfoMessage =
          this.canCreateAccount || !!this.user?.systemMessage;

        this.hasPromotion = this.user
          ? !!this.user.subscription?.offer?.coupon ||
            !!this.user.subscription?.offer?.durationExtension
          : !!this.info?.subscriptionOffer?.coupon ||
            !!this.info?.subscriptionOffer?.durationExtension;

        this.initializeTheme(this.user?.settings.colorScheme);

        this.changeDetectorRef.markForCheck();
      });
  }

  public onClickSystemMessage() {
    if (this.user.systemMessage.routerLink) {
      this.router.navigate(this.user.systemMessage.routerLink);
    } else {
      this.notificationService.alert({
        title: this.user.systemMessage.message
      });
    }
  }

  public onCreateAccount() {
    this.tokenStorageService.signOut();
  }

  public onSignOut() {
    this.tokenStorageService.signOut();
    this.userService.remove();

    document.location.href = `/${document.documentElement.lang}`;
  }

  public ngOnDestroy() {
    this.unsubscribeSubject.next();
    this.unsubscribeSubject.complete();
  }

  private updateRouteFromRouter(): void {
    const urlTree = this.router.parseUrl(this.router.url);
    const urlSegmentGroup = urlTree.root.children[PRIMARY_OUTLET];
    const urlSegments = urlSegmentGroup?.segments ?? [];
    this.currentRoute = urlSegments[0]?.path;
    this.currentSubRoute = urlSegments[1]?.path;
  }

  private initializeTheme(userPreferredColorScheme?: ColorScheme) {
    const isDarkTheme = userPreferredColorScheme
      ? userPreferredColorScheme === 'DARK'
      : window.matchMedia('(prefers-color-scheme: dark)').matches;

    this.toggleTheme(isDarkTheme);

    window.matchMedia('(prefers-color-scheme: dark)').addListener((event) => {
      if (!this.user?.settings.colorScheme) {
        this.toggleTheme(event.matches);
      }
    });
  }

  private openHoldingDetailDialog({
    dataSource,
    symbol
  }: {
    dataSource: DataSource;
    symbol: string;
  }) {
    this.userService
      .get()
      .pipe(takeUntil(this.unsubscribeSubject))
      .subscribe((user) => {
        this.user = user;

        const dialogRef = this.dialog.open<
          GfHoldingDetailDialogComponent,
          HoldingDetailDialogParams
        >(GfHoldingDetailDialogComponent, {
          autoFocus: false,
          data: {
            dataSource,
            symbol,
            baseCurrency: this.user?.settings?.baseCurrency,
            colorScheme: this.user?.settings?.colorScheme,
            deviceType: this.deviceType,
            hasImpersonationId: this.hasImpersonationId,
            hasPermissionToAccessAdminControl: hasPermission(
              this.user?.permissions,
              permissions.accessAdminControl
            ),
            hasPermissionToCreateActivity:
              !this.hasImpersonationId &&
              hasPermission(this.user?.permissions, permissions.createOrder) &&
              !this.user?.settings?.isRestrictedView,
            hasPermissionToReportDataGlitch: hasPermission(
              this.user?.permissions,
              permissions.reportDataGlitch
            ),
            hasPermissionToUpdateOrder:
              !this.hasImpersonationId &&
              hasPermission(this.user?.permissions, permissions.updateOrder) &&
              !this.user?.settings?.isRestrictedView,
            locale: this.user?.settings?.locale
          },
          height: this.deviceType === 'mobile' ? '98vh' : '80vh',
          width: this.deviceType === 'mobile' ? '100vw' : '50rem'
        });

        dialogRef
          .afterClosed()
          .pipe(takeUntil(this.unsubscribeSubject))
          .subscribe(() => {
            this.router.navigate([], {
              queryParams: {
                dataSource: null,
                holdingDetailDialog: null,
                symbol: null
              },
              queryParamsHandling: 'merge',
              relativeTo: this.route
            });
          });
      });
  }

  private toggleTheme(isDarkTheme: boolean) {
    const themeColor = getCssVariable(
      isDarkTheme ? '--dark-background' : '--light-background'
    );

    if (isDarkTheme) {
      this.document.body.classList.add('theme-dark');
    } else {
      this.document.body.classList.remove('theme-dark');
    }

    this.document
      .querySelector('meta[name="theme-color"]')
      .setAttribute('content', themeColor);
  }
}
