import { create } from 'zustand'
import type { FileData, Selection, ReviewResponse, ProjectData } from '../types'

interface ReviewStore {
  file: FileData | null
  selection: Selection | null
  responses: ReviewResponse[]
  highlightLines: { start: number; end: number } | null
  project: ProjectData | null
  projectMode: boolean
  summaryLoading: boolean
  summaryReady: boolean

  setFile: (file: FileData) => void
  setSelection: (sel: Selection | null) => void
  addResponse: (resp: ReviewResponse) => void
  updateResponseContent: (id: string, content: string) => void
  setResponseDone: (id: string) => void
  setHighlightLines: (lines: { start: number; end: number } | null) => void
  setProject: (project: ProjectData) => void
  selectProjectFile: (path: string) => void
  clearProject: () => void
  setSummaryLoading: (loading: boolean) => void
  setSummaryReady: (ready: boolean) => void
}

export const useReviewStore = create<ReviewStore>((set, get) => ({
  file: null,
  selection: null,
  responses: [],
  highlightLines: null,
  project: null,
  projectMode: false,
  summaryLoading: false,
  summaryReady: false,

  setFile: (file) => set({ file, selection: null, responses: [] }),
  setSelection: (selection) => set({ selection }),
  addResponse: (resp) =>
    set((state) => ({ responses: [...state.responses, resp] })),
  updateResponseContent: (id, content) =>
    set((state) => ({
      responses: state.responses.map((r) =>
        r.id === id ? { ...r, content } : r
      ),
    })),
  setResponseDone: (id) =>
    set((state) => ({
      responses: state.responses.map((r) =>
        r.id === id ? { ...r, loading: false } : r
      ),
    })),
  setHighlightLines: (highlightLines) => set({ highlightLines }),

  setProject: (project) => {
    const firstFile = project.files[0]
    const file: FileData | null = firstFile
      ? { filename: firstFile.path, content: firstFile.content, line_count: firstFile.line_count }
      : null
    set({ project, projectMode: true, file, selection: null, responses: [], summaryLoading: true, summaryReady: false })
  },

  selectProjectFile: (path) => {
    const { project } = get()
    if (!project) return
    const pf = project.files.find((f) => f.path === path)
    if (!pf) return
    set({
      file: { filename: pf.path, content: pf.content, line_count: pf.line_count },
      selection: null,
    })
  },

  clearProject: () => set({ project: null, projectMode: false, file: null, selection: null, responses: [], summaryLoading: false, summaryReady: false }),

  setSummaryLoading: (summaryLoading) => set({ summaryLoading }),
  setSummaryReady: (summaryReady) => set({ summaryReady }),
}))
