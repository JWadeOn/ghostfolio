import { HasPermission } from '@ghostfolio/api/decorators/has-permission.decorator';
import { HasPermissionGuard } from '@ghostfolio/api/guards/has-permission.guard';
import { permissions } from '@ghostfolio/common/permissions';

import {
  Body,
  Controller,
  Get,
  Param,
  Post,
  Req,
  UseGuards
} from '@nestjs/common';
import { AuthGuard } from '@nestjs/passport';
import { Request } from 'express';

import { TradingAgentChatDto } from './trading-agent-chat.dto';
import {
  TradingAgentChatResponse,
  TradingAgentConversationResponse,
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
    @Body() body: TradingAgentChatDto,
    @Req() req: Request
  ): Promise<TradingAgentChatResponse> {
    const accessToken =
      typeof req.headers['authorization'] === 'string'
        ? req.headers['authorization'].replace(/^Bearer\s+/i, '').trim()
        : undefined;
    return this.tradingAgentService.chat(body, accessToken);
  }

  @Get('conversation/:threadId')
  @HasPermission(permissions.readAiPrompt)
  @UseGuards(AuthGuard('jwt'), HasPermissionGuard)
  public async getConversation(
    @Param('threadId') threadId: string
  ): Promise<TradingAgentConversationResponse> {
    return this.tradingAgentService.getConversation(threadId);
  }
}
