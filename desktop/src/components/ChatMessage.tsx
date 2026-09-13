import React, { useState } from 'react';
import { Terminal, Check, Copy, Play, Sparkles, AlertCircle, Loader2 } from 'lucide-react';

export interface ChatMessageData {
  id: number;
  sender: 'user' | 'agent';
  text: string;
  timestamp?: string;
  actionRequired?: boolean;
  command?: string[];
  executable?: boolean;
  executed?: boolean;
  isError?: boolean;
  streaming?: boolean;
}

interface ChatMessageProps {
  message: ChatMessageData;
  isExecuting?: boolean;
  onExecute?: (messageId: number, command?: string[]) => void;
}

/**
 * Formats inline Markdown features: bold (**text**), inline code (`code`), and links.
 */
function renderInlineFormatting(line: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const regex = /(`[^`]+`|\*\*[^*]+\*\*)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(line)) !== null) {
    if (match.index > lastIndex) {
      parts.push(line.substring(lastIndex, match.index));
    }
    const token = match[0];
    if (token.startsWith('`') && token.endsWith('`')) {
      const codeText = token.slice(1, -1);
      parts.push(
        <code
          key={`code-${match.index}`}
          className="px-1.5 py-0.5 rounded bg-black/40 border border-border-subtle text-accent font-mono text-[11px]"
        >
          {codeText}
        </code>
      );
    } else if (token.startsWith('**') && token.endsWith('**')) {
      const boldText = token.slice(2, -2);
      parts.push(
        <strong key={`bold-${match.index}`} className="font-semibold text-white">
          {boldText}
        </strong>
      );
    }
    lastIndex = regex.lastIndex;
  }

  if (lastIndex < line.length) {
    parts.push(line.substring(lastIndex));
  }

  return parts.length > 0 ? parts : [line];
}

/**
 * Parses markdown text into formatted blocks: code blocks, lists, and paragraphs.
 */
function MarkdownRenderer({ content }: { content: string }) {
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

  const handleCopy = (codeText: string, blockIdx: number) => {
    navigator.clipboard.writeText(codeText);
    setCopiedIndex(blockIdx);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  const lines = content.split('\n');
  const elements: React.ReactNode[] = [];
  let inCodeBlock = false;
  let codeLang = '';
  let codeLines: string[] = [];
  let blockIndex = 0;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim().startsWith('```')) {
      if (!inCodeBlock) {
        // Start code block
        inCodeBlock = true;
        codeLang = line.trim().replace('```', '').trim() || 'text';
        codeLines = [];
      } else {
        // End code block
        inCodeBlock = false;
        const currentBlockIdx = blockIndex++;
        const rawCode = codeLines.join('\n');
        elements.push(
          <div
            key={`code-block-${currentBlockIdx}`}
            className="my-2.5 rounded-xl border border-border-subtle bg-[#05070B] overflow-hidden shadow-inner font-mono text-xs"
          >
            <div className="flex items-center justify-between px-3 py-1.5 bg-surface/60 border-b border-border-subtle text-[10px] text-gray-400">
              <span className="uppercase tracking-wider font-semibold text-accent/80">
                {codeLang}
              </span>
              <button
                onClick={() => handleCopy(rawCode, currentBlockIdx)}
                className="flex items-center gap-1 hover:text-white transition-colors cursor-pointer"
                title="Copy code"
              >
                {copiedIndex === currentBlockIdx ? (
                  <>
                    <Check size={12} className="text-accent" />
                    <span className="text-accent text-[10px] font-bold">Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy size={12} />
                    <span>Copy</span>
                  </>
                )}
              </button>
            </div>
            <pre className="p-3 overflow-x-auto text-gray-200 leading-relaxed">
              <code>{rawCode}</code>
            </pre>
          </div>
        );
      }
      continue;
    }

    if (inCodeBlock) {
      codeLines.push(line);
      continue;
    }

    // Bullet points
    if (line.trim().startsWith('- ') || line.trim().startsWith('* ')) {
      const bulletText = line.trim().substring(2);
      elements.push(
        <div key={`bullet-${i}`} className="flex items-start gap-2 my-0.5 ml-1">
          <span className="w-1.5 h-1.5 rounded-full bg-accent mt-1.5 shrink-0" />
          <span>{renderInlineFormatting(bulletText)}</span>
        </div>
      );
      continue;
    }

    // Blank line
    if (line.trim() === '') {
      elements.push(<div key={`blank-${i}`} className="h-2" />);
    } else {
      elements.push(
        <p key={`line-${i}`} className="my-0.5">
          {renderInlineFormatting(line)}
        </p>
      );
    }
  }

  // If code block was unclosed (e.g. streaming)
  if (inCodeBlock && codeLines.length > 0) {
    const rawCode = codeLines.join('\n');
    elements.push(
      <div
        key="code-block-unclosed"
        className="my-2.5 rounded-xl border border-border-subtle bg-[#05070B] overflow-hidden shadow-inner font-mono text-xs"
      >
        <div className="flex items-center justify-between px-3 py-1.5 bg-surface/60 border-b border-border-subtle text-[10px] text-accent/80 font-semibold uppercase">
          <span>{codeLang || 'streaming...'}</span>
        </div>
        <pre className="p-3 overflow-x-auto text-gray-200 leading-relaxed">
          <code>{rawCode}</code>
        </pre>
      </div>
    );
  }

  return <div className="space-y-1">{elements}</div>;
}

export default function ChatMessage({ message, isExecuting = false, onExecute }: ChatMessageProps) {
  const isUser = message.sender === 'user';
  const [copiedCommand, setCopiedCommand] = useState(false);

  const handleCopyCmd = () => {
    if (!message.command) return;
    const fullCmd = `prash ${message.command.join(' ')}`;
    navigator.clipboard.writeText(fullCmd);
    setCopiedCommand(true);
    setTimeout(() => setCopiedCommand(false), 2000);
  };

  return (
    <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} group`}>
      {/* Sender Tag / Icon for Agent */}
      {!isUser && (
        <div className="flex items-center gap-1.5 mb-1 px-1 text-[11px] font-semibold text-gray-400">
          <Sparkles size={13} className="text-accent" />
          <span>Lear Copilot</span>
          {message.timestamp && (
            <span className="text-[10px] text-gray-500 font-normal">
              {message.timestamp}
            </span>
          )}
        </div>
      )}

      {/* Main Message Bubble */}
      <div
        className={`max-w-[90%] p-4 rounded-2xl text-xs leading-relaxed transition-all shadow-md ${
          isUser
            ? 'bg-accent text-gray-950 font-medium rounded-tr-none shadow-accent/10'
            : message.isError
            ? 'bg-red-500/10 border border-red-500/30 text-red-200 rounded-tl-none'
            : 'bg-[#0E131F]/90 border border-border-subtle text-gray-200 rounded-tl-none'
        }`}
      >
        {message.isError && (
          <div className="flex items-center gap-2 mb-2 pb-2 border-b border-red-500/20 text-red-400 font-semibold">
            <AlertCircle size={14} />
            <span>Bridge Exception</span>
          </div>
        )}

        {/* Content Body */}
        {isUser ? (
          <p className="whitespace-pre-wrap">{message.text}</p>
        ) : (
          <div>
            <MarkdownRenderer content={message.text} />
            {message.streaming && (
              <span className="inline-block w-1.5 h-3 ml-1 bg-accent animate-pulse align-middle" />
            )}
          </div>
        )}

        {/* Action Recommendation Card */}
        {message.command && message.command.length > 0 && (
          <div className="mt-3.5 pt-3 border-t border-border-subtle flex flex-col gap-2.5">
            <div className="flex items-center justify-between text-[11px] font-mono text-gray-400 bg-black/40 px-2.5 py-1.5 rounded-lg border border-border-subtle">
              <div className="flex items-center gap-2 overflow-x-auto">
                <Terminal size={13} className="text-accent shrink-0" />
                <code className="text-gray-200 font-bold whitespace-nowrap">
                  prash {message.command.join(' ')}
                </code>
              </div>
              <button
                onClick={handleCopyCmd}
                className="ml-2 hover:text-white transition-colors cursor-pointer shrink-0"
                title="Copy command"
              >
                {copiedCommand ? (
                  <Check size={13} className="text-accent" />
                ) : (
                  <Copy size={13} />
                )}
              </button>
            </div>

            {message.executed ? (
              <div className="flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg bg-accent/10 border border-accent/30 text-accent font-semibold text-xs">
                <Check size={14} />
                <span>Action Dispatched & Telemetry Synced</span>
              </div>
            ) : (
              <button
                onClick={() => onExecute && onExecute(message.id, message.command)}
                disabled={isExecuting}
                className="flex items-center justify-center gap-2 w-full py-2 px-3 rounded-lg bg-accent text-gray-950 hover:bg-accent-light font-bold text-xs transition-all cursor-pointer shadow-md disabled:opacity-50"
              >
                {isExecuting ? (
                  <>
                    <Loader2 size={13} className="animate-spin" />
                    <span>Executing Action Pipeline...</span>
                  </>
                ) : (
                  <>
                    <Play size={13} />
                    <span>Execute Action</span>
                  </>
                )}
              </button>
            )}
          </div>
        )}
      </div>

      {/* User Timestamp */}
      {isUser && message.timestamp && (
        <span className="text-[10px] text-gray-500 font-normal mt-1 mr-1">
          {message.timestamp}
        </span>
      )}
    </div>
  );
}
