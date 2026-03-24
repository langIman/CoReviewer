import { create } from 'zustand'
import type { FileData, Selection, ReviewResponse } from '../types'

interface ReviewStore {
  file: FileData | null
  selection: Selection | null
  responses: ReviewResponse[]
  highlightLines: { start: number; end: number } | null

  setFile: (file: FileData) => void
  setSelection: (sel: Selection | null) => void
  addResponse: (resp: ReviewResponse) => void
  updateResponseContent: (id: string, content: string) => void
  setResponseDone: (id: string) => void
  setHighlightLines: (lines: { start: number; end: number } | null) => void
}

export const useReviewStore = create<ReviewStore>((set) => ({
  file: null,
  selection: null,
  responses: [],
  highlightLines: null,

  setFile: (file) => set({ file, selection: null, responses: [] }),
  setSelection: (selection) => set({ selection }),
  addResponse: (resp) =>
    set((state) => ({ responses: [resp, ...state.responses] })),
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
}))
