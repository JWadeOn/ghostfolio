import { ConfigurationService } from '@ghostfolio/api/services/configuration/configuration.service';

import { Injectable } from '@nestjs/common';
import { HttpException } from '@nestjs/common';
import { StatusCodes } from 'http-status-codes';

const CHAT_TIMEOUT_MS = 60_000;

export interface TradingAgentChatRequest {
  message: string;
  thread_id?: string;
}

export interface TradingAgentChatResponse {
  response: Record<string, unknown>;
  thread_id: string;
}

@Injectable()
export class TradingAgentService {
  public constructor(
    private readonly configurationService: ConfigurationService
  ) {}

  public async chat(
    body: TradingAgentChatRequest,
    accessToken?: string
  ): Promise<TradingAgentChatResponse> {
    const baseUrl = this.configurationService.get('TRADING_AGENT_URL');
    if (!baseUrl?.trim()) {
      throw new HttpException(
        { error: 'Trading agent is not configured' },
        StatusCodes.SERVICE_UNAVAILABLE
      );
    }

    const url = `${baseUrl.replace(/\/$/, '')}/api/chat`;

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS);

    const payload: Record<string, unknown> = {
      message: body.message,
      thread_id: body.thread_id ?? undefined
    };
    if (accessToken) {
      payload.access_token = accessToken;
    }

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const text = await response.text();
        throw new HttpException(
          {
            error:
              response.status >= 500
                ? 'Trading agent is unavailable'
                : text || response.statusText
          },
          response.status >= 500 ? StatusCodes.BAD_GATEWAY : response.status
        );
      }

      const data = (await response.json()) as TradingAgentChatResponse;
      return data;
    } catch (error) {
      clearTimeout(timeoutId);
      if (error instanceof HttpException) {
        throw error;
      }
      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          throw new HttpException(
            { error: 'Trading agent request timed out' },
            StatusCodes.GATEWAY_TIMEOUT
          );
        }
        throw new HttpException(
          { error: 'Trading agent is unavailable' },
          StatusCodes.BAD_GATEWAY
        );
      }
      throw new HttpException(
        { error: 'Trading agent is unavailable' },
        StatusCodes.BAD_GATEWAY
      );
    }
  }
}
