import { useWikiStore } from '../../store/useWikiStore'
import MarkdownRenderer from './MarkdownRenderer'
import type { WikiPage } from '../../types/wiki'

export default function WikiPageView() {
  const wiki = useWikiStore((s) => s.wiki)
  const currentPageId = useWikiStore((s) => s.currentPageId)

  if (!wiki || !currentPageId) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
        未选择页面
      </div>
    )
  }

  const page = wiki.pages.find((p) => p.id === currentPageId)

  if (!page) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
        页面不存在
      </div>
    )
  }

  // category 节点理论上不应被导航到，防御性返回
  if (page.type === 'category') {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
        请从左侧选择具体页面
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-auto">
      <div className="max-w-4xl mx-auto px-8 py-6">
        <header className="mb-4 pb-3 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 mb-1">
            <span>{labelFor(page.type)}</span>
            {page.path && (
              <>
                <span>·</span>
                <code className="font-mono">{page.path}</code>
              </>
            )}
          </div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{page.title}</h1>
        </header>
        {page.content_md ? (
          <MarkdownRenderer content={page.content_md} />
        ) : (
          <p className="text-sm text-gray-400">该页面无内容</p>
        )}
      </div>
    </div>
  )
}

function labelFor(type: Exclude<WikiPage['type'], 'category'>): string {
  switch (type) {
    case 'overview':
      return '项目概览'
    case 'chapter':
      return '核心架构'
    case 'topic':
      return '专题深入'
    case 'module':
      return '模块'
  }
}
