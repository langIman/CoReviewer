import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import locales, { type Lang } from './locales'

interface LanguageContextType {
  lang: Lang
  toggleLang: () => void
  t: (key: string) => string
}

const LanguageContext = createContext<LanguageContextType>(null!)

function getInitialLang(): Lang {
  const saved = localStorage.getItem('coreviewer-lang')
  if (saved === 'zh' || saved === 'en') return saved
  return 'en'
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(getInitialLang)

  const toggleLang = useCallback(() => {
    setLang((prev) => {
      const next = prev === 'zh' ? 'en' : 'zh'
      localStorage.setItem('coreviewer-lang', next)
      return next
    })
  }, [])

  const t = useCallback(
    (key: string) => locales[lang][key] ?? key,
    [lang]
  )

  return (
    <LanguageContext.Provider value={{ lang, toggleLang, t }}>
      {children}
    </LanguageContext.Provider>
  )
}

export function useLanguage() {
  return useContext(LanguageContext)
}
