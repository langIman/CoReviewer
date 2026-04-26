import { create } from 'zustand'
import type {
  Conversation,
  QAMessage,
  QAMode,
  ToolEvent,
} from '../types/qa'
import type { CodeRef } from '../types/wiki'
import {
  deleteConversation as apiDeleteConversation,
  getConversation,
  listConversations,
  streamAsk,
} from '../services/qaApi'
import { useWikiStore } from './useWikiStore'

const MODE_STORAGE_KEY = 'coreviewer.qa.mode'
const WIDTH_STORAGE_KEY = 'coreviewer.qa.widthRatio'
const MIN_WIDTH = 0.25
const MAX_WIDTH = 0.6
const DEFAULT_WIDTH = 0.35

function loadMode(): QAMode {
  try {
    const v = localStorage.getItem(MODE_STORAGE_KEY)
    return v === 'deep' ? 'deep' : 'fast'
  } catch {
    return 'fast'
  }
}

function loadWidth(): number {
  try {
    const v = Number(localStorage.getItem(WIDTH_STORAGE_KEY))
    if (Number.isFinite(v) && v >= MIN_WIDTH && v <= MAX_WIDTH) return v
  } catch {
    // ignore
  }
  return DEFAULT_WIDTH
}

interface PendingAssistant {
  content: string
  toolEvents: ToolEvent[]
  codeRefs: Record<string, CodeRef>
  budgetExhausted: boolean
  mode: QAMode
}

interface QAStore {
  open: boolean
  widthRatio: number

  conversations: Conversation[]
  conversationsLoaded: boolean
  currentConversationId: string | null
  currentTitle: string | null

  messages: QAMessage[]
  streaming: boolean
  streamError: string | null
  streamController: AbortController | null
  pendingAssistant: PendingAssistant | null

  mode: QAMode

  toggleOpen: () => void
  setOpen: (open: boolean) => void
  setWidthRatio: (r: number) => void
  setMode: (m: QAMode) => void

  loadConversations: (projectName: string) => Promise<void>
  selectConversation: (id: string) => Promise<void>
  newConversation: () => void
  deleteConversation: (id: string) => Promise<void>

  ask: (question: string, projectName: string) => Promise<void>
  cancelStream: () => void

  openCodeRef: (ref: CodeRef) => void

  reset: () => void
}

function nowIso() {
  return new Date().toISOString()
}

export const useQAStore = create<QAStore>((set, get) => ({
  open: false,
  widthRatio: loadWidth(),

  conversations: [],
  conversationsLoaded: false,
  currentConversationId: null,
  currentTitle: null,

  messages: [],
  streaming: false,
  streamError: null,
  streamController: null,
  pendingAssistant: null,

  mode: loadMode(),

  toggleOpen: () => set((s) => ({ open: !s.open })),
  setOpen: (open) => set({ open }),

  setWidthRatio: (r) => {
    const clamped = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, r))
    try {
      localStorage.setItem(WIDTH_STORAGE_KEY, String(clamped))
    } catch {
      // ignore
    }
    set({ widthRatio: clamped })
  },

  setMode: (m) => {
    try {
      localStorage.setItem(MODE_STORAGE_KEY, m)
    } catch {
      // ignore
    }
    set({ mode: m })
  },

  loadConversations: async (projectName) => {
    try {
      const list = await listConversations(projectName)
      set({ conversations: list, conversationsLoaded: true })
    } catch (e) {
      set({
        conversations: [],
        conversationsLoaded: true,
        streamError: e instanceof Error ? e.message : '加载会话列表失败',
      })
    }
  },

  selectConversation: async (id) => {
    get().cancelStream()
    try {
      const detail = await getConversation(id)
      set({
        currentConversationId: detail.id,
        currentTitle: detail.title,
        messages: detail.messages,
        pendingAssistant: null,
        streamError: null,
      })
    } catch (e) {
      set({
        streamError: e instanceof Error ? e.message : '加载会话失败',
      })
    }
  },

  newConversation: () => {
    get().cancelStream()
    set({
      currentConversationId: null,
      currentTitle: null,
      messages: [],
      pendingAssistant: null,
      streamError: null,
    })
  },

  deleteConversation: async (id) => {
    try {
      await apiDeleteConversation(id)
      set((s) => {
        const conversations = s.conversations.filter((c) => c.id !== id)
        const isCurrent = s.currentConversationId === id
        return {
          conversations,
          currentConversationId: isCurrent ? null : s.currentConversationId,
          currentTitle: isCurrent ? null : s.currentTitle,
          messages: isCurrent ? [] : s.messages,
          pendingAssistant: isCurrent ? null : s.pendingAssistant,
        }
      })
    } catch (e) {
      set({ streamError: e instanceof Error ? e.message : '删除会话失败' })
    }
  },

  ask: async (question, projectName) => {
    const trimmed = question.trim()
    if (!trimmed || get().streaming) return

    const { mode, currentConversationId } = get()
    const ctrl = new AbortController()

    const userMsg: QAMessage = {
      id: -Date.now(),
      conversation_id: currentConversationId ?? '',
      role: 'user',
      content: trimmed,
      tool_events: [],
      code_refs: {},
      created_at: nowIso(),
    }

    set((s) => ({
      messages: [...s.messages, userMsg],
      streaming: true,
      streamError: null,
      streamController: ctrl,
      pendingAssistant: {
        content: '',
        toolEvents: [],
        codeRefs: {},
        budgetExhausted: false,
        mode,
      },
    }))

    try {
      for await (const evt of streamAsk(
        {
          project_name: projectName,
          conversation_id: currentConversationId,
          question: trimmed,
          mode,
        },
        ctrl.signal,
      )) {
        switch (evt.event) {
          case 'start': {
            set({
              currentConversationId: evt.data.conversation_id,
              currentTitle: get().currentTitle ?? trimmed.slice(0, 30),
            })
            break
          }
          case 'token': {
            set((s) =>
              s.pendingAssistant
                ? {
                    pendingAssistant: {
                      ...s.pendingAssistant,
                      content: s.pendingAssistant.content + evt.data.delta,
                    },
                  }
                : {},
            )
            break
          }
          case 'tool_call': {
            set((s) =>
              s.pendingAssistant
                ? {
                    pendingAssistant: {
                      ...s.pendingAssistant,
                      toolEvents: [
                        ...s.pendingAssistant.toolEvents,
                        {
                          phase: 'call',
                          iteration: evt.data.iteration,
                          name: evt.data.name,
                          args_preview: evt.data.args_preview,
                        },
                      ],
                    },
                  }
                : {},
            )
            break
          }
          case 'tool_result': {
            set((s) =>
              s.pendingAssistant
                ? {
                    pendingAssistant: {
                      ...s.pendingAssistant,
                      toolEvents: [
                        ...s.pendingAssistant.toolEvents,
                        {
                          phase: 'result',
                          iteration: evt.data.iteration,
                          name: evt.data.name,
                          ok: evt.data.ok,
                          preview: evt.data.preview,
                        },
                      ],
                    },
                  }
                : {},
            )
            break
          }
          case 'budget_exhausted': {
            set((s) =>
              s.pendingAssistant
                ? {
                    pendingAssistant: {
                      ...s.pendingAssistant,
                      budgetExhausted: true,
                    },
                  }
                : {},
            )
            break
          }
          case 'code_refs': {
            set((s) =>
              s.pendingAssistant
                ? {
                    pendingAssistant: {
                      ...s.pendingAssistant,
                      codeRefs: evt.data.refs ?? {},
                    },
                  }
                : {},
            )
            break
          }
          case 'done': {
            const pending = get().pendingAssistant
            const convId = get().currentConversationId ?? ''
            if (pending) {
              // 后端 done 事件若带净化后的 content（去 code_refs 块），优先使用
              const finalContent = evt.data.content ?? pending.content
              const assistantMsg: QAMessage = {
                id: evt.data.assistant_message_id,
                conversation_id: convId,
                role: 'assistant',
                content: finalContent,
                mode: pending.mode,
                tool_events: pending.toolEvents,
                code_refs: pending.codeRefs,
                budget_exhausted: pending.budgetExhausted,
                created_at: nowIso(),
              }
              set((s) => ({
                messages: [...s.messages, assistantMsg],
                pendingAssistant: null,
              }))
            }
            break
          }
          case 'error': {
            set({ streamError: evt.data.message })
            break
          }
        }
      }
    } catch (e) {
      if (ctrl.signal.aborted) {
        set({ pendingAssistant: null })
      } else {
        const msg = e instanceof Error ? e.message : '问答请求失败'
        set({ streamError: msg, pendingAssistant: null })
      }
    } finally {
      set({ streaming: false, streamController: null })
      // 刷新会话列表（标题/updated_at 可能变化）
      if (!ctrl.signal.aborted && projectName) {
        void get().loadConversations(projectName)
      }
    }
  },

  cancelStream: () => {
    const ctrl = get().streamController
    if (ctrl) {
      try {
        ctrl.abort()
      } catch {
        // ignore
      }
    }
    set({ streamController: null })
  },

  openCodeRef: (ref) => {
    useWikiStore.getState().openCodeDrawerWithRef(ref)
  },

  reset: () => {
    get().cancelStream()
    set({
      open: false,
      conversations: [],
      conversationsLoaded: false,
      currentConversationId: null,
      currentTitle: null,
      messages: [],
      streaming: false,
      streamError: null,
      streamController: null,
      pendingAssistant: null,
    })
  },
}))
