import { AuthGuard } from '@ghostfolio/client/core/auth.guard';
import { internalRoutes } from '@ghostfolio/common/routes/routes';

import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    canActivate: [AuthGuard],
    loadComponent: () =>
      import('./trading-agent-page.component').then(
        (m) => m.GfTradingAgentPageComponent
      ),
    path: '',
    title: internalRoutes.tradingAgent.title
  }
];
