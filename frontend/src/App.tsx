import UploadBar from './components/UploadBar'
import CodeView from './components/CodeView/CodeView'
import ActionBar from './components/ActionBar'
import AIPanel from './components/AIPanel/AIPanel'

export default function App() {
  return (
    <div className="flex flex-col h-screen bg-white">
      <UploadBar />
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Code View */}
        <div className="flex flex-col w-1/2 border-r border-gray-200">
          <CodeView />
          <ActionBar />
        </div>
        {/* Right: AI Panel */}
        <div className="w-1/2">
          <AIPanel />
        </div>
      </div>
    </div>
  )
}
