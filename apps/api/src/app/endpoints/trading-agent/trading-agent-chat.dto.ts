import { IsOptional, IsString } from 'class-validator';

export class TradingAgentChatDto {
  @IsString()
  message: string;

  @IsString()
  @IsOptional()
  thread_id?: string;
}
