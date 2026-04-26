import { useQAStore } from '../../store/useQAStore'

export default function QAHandle() {
  const open = useQAStore((s) => s.open)
  const widthRatio = useQAStore((s) => s.widthRatio)
  const toggleOpen = useQAStore((s) => s.toggleOpen)

  const rightStyle = open ? `${widthRatio * 100}vw` : '0px'

  return (
    <button
      onClick={toggleOpen}
      aria-label={open ? '收起问答面板' : '展开问答面板'}
      title={open ? '收起问答' : '打开问答'}
      className="group fixed top-1/2 -translate-y-1/2 z-30 h-14 w-4 flex flex-col items-center justify-center gap-1
                 bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm
                 hover:bg-gray-50 dark:hover:bg-gray-700
                 text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300
                 shadow-sm hover:shadow
                 rounded-l-md border border-r-0 border-gray-200 dark:border-gray-700
                 transition-[right,background-color,color] duration-200"
      style={{ right: rightStyle }}
    >
      <svg
        width="10"
        height="10"
        viewBox="0 0 10 10"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {open ? (
          <path d="M3.5 2 L6.5 5 L3.5 8" />
        ) : (
          <path d="M6.5 2 L3.5 5 L6.5 8" />
        )}
      </svg>
      {!open && (
        <span
          className="text-[9px] leading-none writing-vertical text-gray-400 group-hover:text-gray-600 dark:text-gray-500 dark:group-hover:text-gray-300"
          style={{ writingMode: 'vertical-rl' }}
        >
          问答
        </span>
      )}
    </button>
  )
}
