import { ConfigurationModule } from '@ghostfolio/api/services/configuration/configuration.module';
import { UserModule } from '@ghostfolio/api/app/user/user.module';

import { Module } from '@nestjs/common';

import { TradingAgentController } from './trading-agent.controller';
import { TradingAgentService } from './trading-agent.service';

@Module({
  controllers: [TradingAgentController],
  imports: [ConfigurationModule, UserModule],
  providers: [TradingAgentService]
})
export class TradingAgentModule {}
