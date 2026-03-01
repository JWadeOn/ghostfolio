import { IsOptional, IsString } from 'class-validator';

export class TradingAgentFeedbackDto {
  @IsString()
  thread_id: string;

  @IsString()
  rating: 'thumbs_up' | 'thumbs_down';

  @IsString()
  @IsOptional()
  correction?: string;

  @IsString()
  @IsOptional()
  comment?: string;
}
