import { HasPermission } from '@ghostfolio/api/decorators/has-permission.decorator';
import { HasPermissionGuard } from '@ghostfolio/api/guards/has-permission.guard';
import { permissions } from '@ghostfolio/common/permissions';

import { Body, Controller, Post, UseGuards } from '@nestjs/common';
import { AuthGuard } from '@nestjs/passport';

import { TradingAgentChatDto } from './trading-agent-chat.dto';
import {
  TradingAgentChatResponse,
  TradingAgentService
} from './trading-agent.service';

@Controller('trading-agent')
export class TradingAgentController {
  public constructor(
    private readonly tradingAgentService: TradingAgentService
  ) {}

  @Post('chat')
  @HasPermission(permissions.readAiPrompt)
  @UseGuards(AuthGuard('jwt'), HasPermissionGuard)
  public async chat(
    @Body() body: TradingAgentChatDto
  ): Promise<TradingAgentChatResponse> {
    return this.tradingAgentService.chat(body);
  }
}
