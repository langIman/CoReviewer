import { create } from 'zustand'
import type { CodeRef, WikiDocument, WikiPage, WikiProgressEvent, WikiTaskStatus } from '../types/wiki'
import { getPersistedProject, getWikiDocument } from '../services/api'

interface CodeDrawerState {
  open: boolean
  ref: CodeRef | null
}

const PROJECT_NAME_STORAGE_KEY = 'coreviewer.wiki.projectName'

function persistProjectName(name: string | null) {
  try {
    if (name) localStorage.setItem(PROJECT_NAME_STORAGE_KEY, name)
    else localStorage.removeItem(PROJECT_NAME_STORAGE_KEY)
  } catch {
    // ignore
  }
}

function loadPersistedProjectName(): string | null {
  try {
    return localStorage.getItem(PROJECT_NAME_STORAGE_KEY)
  } catch {
    return null
  }
}

interface WikiStore {
  projectName: string | null
  projectFiles: Record<string, string>

  generateTaskId: string | null
  generateStatus: 'idle' | WikiTaskStatus
  generateMessage: string | null
  generateEvents: WikiProgressEvent[]
  lastGenerationDurationMs: number | null

  wiki: WikiDocument | null
  currentPageId: string | null

  rehydrating: boolean

  codeDrawer: CodeDrawerState
  drawerHeightRatio: number

  setProject: (name: string, files: Record<string, string>) => void
  setGenerateTaskId: (id: string | null) => void
  setGenerateStatus: (status: 'idle' | WikiTaskStatus, message?: string | null) => void
  setGenerateEvents: (events: WikiProgressEvent[]) => void
  setLastGenerationDurationMs: (ms: number | null) => void
  setWiki: (doc: WikiDocument) => void

  rehydrateFromStorage: () => Promise<void>

  navigateToPage: (pageId: string) => void
  openCodeDrawer: (refId: string) => void
  openCodeDrawerWithRef: (ref: CodeRef) => void
  closeCodeDrawer: () => void
  setDrawerHeightRatio: (r: number) => void
  reset: () => void
}

export const useWikiStore = create<WikiStore>((set, get) => ({
  projectName: null,
  projectFiles: {},

  generateTaskId: null,
  generateStatus: 'idle',
  generateMessage: null,
  generateEvents: [],
  lastGenerationDurationMs: null,

  wiki: null,
  currentPageId: null,

  rehydrating: false,

  codeDrawer: { open: false, ref: null },
  drawerHeightRatio: 0.4,

  setProject: (name, files) => {
    persistProjectName(name)
    set({ projectName: name, projectFiles: files })
  },

  rehydrateFromStorage: async () => {
    const name = loadPersistedProjectName()
    if (!name) return
    set({ rehydrating: true, projectName: name })
    try {
      // 并发拉 wiki 文档和项目源码：wiki 必须有，源码缺失只关闭 drawer 不致命
      const [doc, projectRes] = await Promise.all([
        getWikiDocument(name),
        getPersistedProject(name).catch((e) => {
          console.warn('[rehydrateFromStorage] 项目源码加载失败，drawer 将不可用:', e)
          return null
        }),
      ])
      const filesMap: Record<string, string> = {}
      if (projectRes) {
        for (const f of projectRes.files) filesMap[f.path] = f.content
      }
      set({
        wiki: doc,
        currentPageId: doc.index.root,
        projectFiles: filesMap,
      })
    } catch (e) {
      console.warn('[rehydrateFromStorage] 加载已保存项目失败，回退到上传页:', e)
      persistProjectName(null)
      set({ projectName: null })
    } finally {
      set({ rehydrating: false })
    }
  },

  setGenerateTaskId: (id) => set({ generateTaskId: id }),
  setGenerateStatus: (status, message = null) =>
    set({ generateStatus: status, generateMessage: message }),
  setGenerateEvents: (events) => set({ generateEvents: events }),
  setLastGenerationDurationMs: (ms) => set({ lastGenerationDurationMs: ms }),

  setWiki: (doc) =>
    set({
      wiki: doc,
      currentPageId: doc.index.root,
    }),

  navigateToPage: (pageId) => {
    const { wiki } = get()
    if (!wiki) return
    const page = wiki.pages.find((p) => p.id === pageId)
    if (!page) return
    // 分类节点不可导航
    if (page.type === 'category') return
    set({ currentPageId: pageId, codeDrawer: { open: false, ref: null } })
  },

  openCodeDrawer: (refId) => {
    const { wiki, currentPageId } = get()
    if (!wiki || !currentPageId) return
    const page = wiki.pages.find((p) => p.id === currentPageId)
    if (!page) return
    const ref = page.metadata.code_refs[refId]
    if (!ref) return
    set({ codeDrawer: { open: true, ref } })
  },

  openCodeDrawerWithRef: (ref) => set({ codeDrawer: { open: true, ref } }),

  closeCodeDrawer: () => set({ codeDrawer: { open: false, ref: null } }),

  setDrawerHeightRatio: (r) =>
    set({ drawerHeightRatio: Math.max(0.2, Math.min(0.75, r)) }),

  reset: () => {
    persistProjectName(null)
    set({
      projectName: null,
      projectFiles: {},
      generateTaskId: null,
      generateStatus: 'idle',
      generateMessage: null,
      generateEvents: [],
      lastGenerationDurationMs: null,
      wiki: null,
      currentPageId: null,
      codeDrawer: { open: false, ref: null },
    })
  },
}))

export type { WikiPage }
