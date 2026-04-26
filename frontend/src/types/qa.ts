import type { CodeRef } from './wiki'

export type QAMode = 'fast' | 'deep'

export interface ToolEvent {
  iteration: number
  name: string
  args?: unknown
  args_preview?: unknown
  ok?: boolean
  preview?: string
  phase: 'call' | 'result'
}

export interface QAMessage {
  id: number
  conversation_id: string
  role: 'user' | 'assistant'
  content: string
  mode?: QAMode | null
  tool_events: ToolEvent[]
  code_refs: Record<string, CodeRef>
  budget_exhausted?: boolean
  created_at: string
}

export interface Conversation {
  id: string
  project_name: string
  title: string
  created_at: string
  updated_at: string
}

export interface ConversationDetail extends Conversation {
  messages: QAMessage[]
}

export interface QARequest {
  project_name: string
  conversation_id?: string | null
  question: string
  mode: QAMode
}

export type SSEEvent =
  | { event: 'start'; data: { conversation_id: string; user_message_id: number; mode: QAMode } }
  | { event: 'token'; data: { delta: string } }
  | {
      event: 'tool_call'
      data: { iteration: number; name: string; args_preview: unknown }
    }
  | {
      event: 'tool_result'
      data: { iteration: number; name: string; ok: boolean; preview: string }
    }
  | { event: 'budget_exhausted'; data: { tokens_est: number; budget: number } }
  | { event: 'code_refs'; data: { refs: Record<string, CodeRef> } }
  | {
      event: 'done'
      data: { assistant_message_id: number; content?: string }
    }
  | { event: 'error'; data: { message: string } }
