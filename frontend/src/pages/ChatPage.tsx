import { useState, useRef, useEffect } from 'react'
import { Menu, Send, ScanLine, Sparkles, Bug, Video } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { useStore } from '../store/useStore'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
}

// TODO: Remove - debugging only
interface DebugState {
  status: string
  inventory: Array<{ name: string; category: string; quantity: number }>
  item_count: number
  last_updated?: string
  latest_image_url?: string
}

interface ChatPageProps {
  onMenuOpen: () => void
  onCameraOpen: () => void
  user: { name: string; email: string } | null
}

export default function ChatPage({ onMenuOpen, onCameraOpen, user }: ChatPageProps) {
  const { blinkConnected } = useStore()
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      role: 'assistant',
      content: 'Hello! How can I help you today?'
    }
  ])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [debugState, setDebugState] = useState<DebugState | null>(null)  // TODO: Remove - debugging only
  const [showDebug, setShowDebug] = useState(false)  // TODO: Remove - debugging only
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const generateId = () => Math.random().toString(36).substring(2) + Date.now().toString(36)

  const handleSend = async () => {
    const message = input.trim()
    if (!message || isLoading) return

    // Add user message
    const userMessage: Message = {
      id: generateId(),
      role: 'user',
      content: message
    }
    setMessages(prev => [...prev, userMessage])
    setInput('')
    setIsLoading(true)

    try {
      const response = await fetch('/api/chat/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message })
      })

      const data = await response.json()

      // TODO: Remove - debugging only
      if (data.debug_state) {
        setDebugState(data.debug_state)
      }

      const assistantMessage: Message = {
        id: generateId(),
        role: 'assistant',
        content: data.response || "I'm sorry, I couldn't process that request."
      }
      setMessages(prev => [...prev, assistantMessage])
    } catch (error) {
      const errorMessage: Message = {
        id: generateId(),
        role: 'assistant',
        content: "Sorry, I'm having trouble connecting. Please try again."
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="h-full flex flex-col max-w-3xl mx-auto">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-white/10">
        <button
          onClick={onMenuOpen}
          className="p-2 hover:bg-white/10 rounded-lg transition-colors"
        >
          <Menu className="w-6 h-6 text-gray-400" />
        </button>

        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-cyan-400" />
          <span className="text-cyan-400 font-medium text-lg">Domus</span>
        </div>

        {/* Camera status indicator */}
        <div className="flex items-center gap-1.5">
          {blinkConnected ? (
            <div className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-green-500/10">
              <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
              <Video className="w-4 h-4 text-green-400" />
            </div>
          ) : (
            <div className="w-10" />
          )}
        </div>
      </header>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`mb-6 ${message.role === 'user' ? 'flex justify-end' : ''}`}
          >
            {message.role === 'assistant' ? (
              <div className="flex gap-3">
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-cyan-400 to-blue-500 flex items-center justify-center flex-shrink-0">
                  <Sparkles className="w-4 h-4 text-white" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-400 mb-1">Domus</p>
                  <div className="text-gray-100 leading-relaxed prose prose-invert prose-sm max-w-none
                    prose-headings:text-cyan-400 prose-headings:font-semibold prose-headings:mt-4 prose-headings:mb-2
                    prose-h2:text-lg prose-h3:text-base
                    prose-p:my-2
                    prose-ul:my-2 prose-li:my-0.5
                    prose-strong:text-cyan-300
                    prose-table:border-collapse prose-table:w-full prose-table:my-3
                    prose-th:bg-cyan-500/20 prose-th:text-cyan-300 prose-th:px-3 prose-th:py-2 prose-th:text-left prose-th:border prose-th:border-white/20
                    prose-td:px-3 prose-td:py-2 prose-td:border prose-td:border-white/10
                    prose-hr:border-white/10 prose-hr:my-4
                  ">
                    <ReactMarkdown>{message.content}</ReactMarkdown>
                  </div>
                </div>
              </div>
            ) : (
              <div className="bg-[#2f2f2f] rounded-2xl px-4 py-3 max-w-[80%]">
                <p className="text-gray-100">{message.content}</p>
              </div>
            )}
          </div>
        ))}

        {isLoading && (
          <div className="flex gap-3 mb-6">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-cyan-400 to-blue-500 flex items-center justify-center flex-shrink-0">
              <Sparkles className="w-4 h-4 text-white" />
            </div>
            <div>
              <p className="text-sm text-gray-400 mb-1">Domus</p>
              <div className="flex gap-1">
                <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* TODO: Remove - Debug Panel */}
      {debugState && (
        <div className="px-4 py-2 border-t border-white/10 bg-yellow-500/5">
          <button
            onClick={() => setShowDebug(!showDebug)}
            className="flex items-center gap-2 text-yellow-400 text-xs font-medium w-full"
          >
            <Bug className="w-3 h-3" />
            Debug: Fridge State ({debugState.item_count} items)
            <span className="text-gray-500 ml-auto">{showDebug ? '▼' : '▶'}</span>
          </button>
          {showDebug && (
            <div className="mt-2 space-y-2">
              {debugState.latest_image_url && (
                <div className="rounded overflow-hidden border border-yellow-500/30">
                  <p className="text-xs text-yellow-400 px-2 py-1 bg-yellow-500/10">Latest Captured Image:</p>
                  <img
                    src={debugState.latest_image_url}
                    alt="Latest fridge capture"
                    className="w-full max-h-48 object-contain bg-black"
                  />
                </div>
              )}
              <div className="p-2 bg-black/30 rounded text-xs font-mono text-gray-300 max-h-40 overflow-y-auto">
                <pre>{JSON.stringify(debugState, null, 2)}</pre>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Input Area */}
      <div className="px-4 pb-4">
        <div className="bg-[#2f2f2f] rounded-full flex items-center px-4 py-2">
          <button
            onClick={onCameraOpen}
            className="p-2 hover:bg-white/10 rounded-full transition-colors"
          >
            <ScanLine className="w-5 h-5 text-gray-400" />
          </button>

          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Message Domus"
            className="flex-1 bg-transparent outline-none text-white placeholder-gray-500 px-3 py-2"
          />

          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="p-2 hover:bg-white/10 rounded-full transition-colors disabled:opacity-50"
          >
            <Send className="w-5 h-5 text-gray-400" />
          </button>
        </div>

        <p className="text-center text-xs text-gray-500 mt-3">
          Domus can make mistakes. Check important info.
        </p>
      </div>
    </div>
  )
}
