import { useEffect } from 'react'
import { useWikiStore } from './store/useWikiStore'
import UploadView from './components/Upload/UploadView'
import WikiLayout from './components/Wiki/WikiLayout'

export default function App() {
  const wiki = useWikiStore((s) => s.wiki)
  const rehydrating = useWikiStore((s) => s.rehydrating)
  const rehydrateFromStorage = useWikiStore((s) => s.rehydrateFromStorage)

  useEffect(() => {
    void rehydrateFromStorage()
  }, [rehydrateFromStorage])

  if (rehydrating) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-50 dark:bg-gray-900">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-3 border-blue-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-gray-600 dark:text-gray-300">正在恢复已保存的项目...</p>
        </div>
      </div>
    )
  }

  return wiki ? <WikiLayout /> : <UploadView />
}
