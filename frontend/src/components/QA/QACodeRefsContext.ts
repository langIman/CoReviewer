import { createContext } from 'react'
import type { CodeRef } from '../../types/wiki'

export const QACodeRefsContext = createContext<Record<string, CodeRef> | null>(null)
