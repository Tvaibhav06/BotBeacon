import React, { useState, useRef, useEffect } from "react";
import { Link } from "react-router-dom";
import {
  Sparkles,
  Send,
  RefreshCw,
  TrendingDown,
  Layers,
  ShieldCheck,
  Zap,
  ArrowRight,
  Bot,
  User,
} from "lucide-react";
import { useAuth } from "../lib/AuthContext";
import { streamCopilotChat, GrowthOpportunity, api } from "../lib/api";
import { Card } from "../design-system/Card";
import { Button } from "../design-system/Button";
import { Badge } from "../design-system/Badge";
import { OpportunityCard } from "../components/OpportunityCard";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  tools?: Array<{ name: string; status: string }>;
  opportunity?: GrowthOpportunity;
}

const STARTER_PROMPTS = [
  "My sales are down. How can I grow?",
  "What are my top declining products?",
  "Find cross-sell opportunities with low attach rates",
];

export function CopilotPage() {
  const { merchantId, token } = useAuth();

  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Hello! I am your **Merchant Growth AI Copilot**. I analyze your store's live sales history, uncover declining trends, identify cross-sell gaps, and formulate deterministic bundle recommendations.\n\nAsk me anything about your catalog or click a starter question below.",
    },
  ]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [activeTools, setActiveTools] = useState<Array<{ name: string; status: string }>>([]);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, activeTools, isStreaming]);

  const handleSend = async (textToSend?: string) => {
    const messageText = (textToSend || input).trim();
    if (!messageText || isStreaming || !merchantId || !token) return;

    setInput("");
    const userMsgId = `user_${Date.now()}`;
    const assistantMsgId = `asst_${Date.now()}`;

    // Add user message and empty assistant placeholder
    setMessages((prev) => [
      ...prev,
      { id: userMsgId, role: "user", content: messageText },
      { id: assistantMsgId, role: "assistant", content: "" },
    ]);

    setIsStreaming(true);
    setActiveTools([]);

    let streamedText = "";
    let proposedOpportunity: GrowthOpportunity | undefined = undefined;

    try {
      await streamCopilotChat(
        merchantId,
        messageText,
        token,
        {
          onChunk: (chunk: string) => {
            streamedText += chunk;
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantMsgId ? { ...msg, content: streamedText } : msg
              )
            );
          },
          onTool: (tool: { name: string; status: string }) => {
            setActiveTools((prev) => {
              const existing = prev.filter((t) => t.name !== tool.name);
              return [...existing, tool];
            });
          },
          onOpportunity: (opp: any) => {
            proposedOpportunity = opp;
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantMsgId
                  ? { ...msg, opportunity: opp }
                  : msg
              )
            );
          },
          onDone: () => {
            setIsStreaming(false);
            setActiveTools([]);
          },
        }
      );
    } catch (err: any) {
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMsgId
            ? {
                ...msg,
                content:
                  msg.content ||
                  `Sorry, I encountered an error while analyzing your request: ${err.message}`,
              }
            : msg
        )
      );
    } finally {
      setIsStreaming(false);
      setActiveTools([]);
    }
  };

  const handleApproveFromChat = async (oppId: string) => {
    if (!merchantId || !token) return;
    await api.approveGrowthOpportunity(merchantId, oppId, token);
    // Refresh opportunity in message state
    setMessages((prev) =>
      prev.map((m) => {
        if (m.opportunity && m.opportunity.id === oppId) {
          return {
            ...m,
            opportunity: {
              ...m.opportunity,
              status: "executing",
            },
          };
        }
        return m;
      })
    );
  };

  const handleRejectFromChat = async (oppId: string) => {
    if (!merchantId || !token) return;
    await api.rejectGrowthOpportunity(merchantId, oppId, token);
    setMessages((prev) =>
      prev.map((m) => {
        if (m.opportunity && m.opportunity.id === oppId) {
          return {
            ...m,
            opportunity: {
              ...m.opportunity,
              status: "rejected_by_merchant",
            },
          };
        }
        return m;
      })
    );
  };

  return (
    <div className="p-6 max-w-5xl h-[calc(100vh-2rem)] flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-border mb-4 shrink-0">
        <div>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-lime flex items-center justify-center text-ink font-bold">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h1 className="font-heading text-lg font-bold text-ink">
                Merchant Growth Copilot
              </h1>
              <p className="font-body text-xs text-ink/50">
                Grounding your business decisions in real database metrics.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Badge variant="surface">
            <ShieldCheck className="w-3 h-3 text-ink mr-1" />
            Double Policy Protected
          </Badge>
          <Link to="/growth">
            <Button variant="outline" size="sm" className="text-xs">
              View Growth Board
            </Button>
          </Link>
        </div>
      </div>

      {/* Messages Scroll Area */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-2 pb-4">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex gap-3 ${
              msg.role === "user" ? "justify-end" : "justify-start"
            }`}
          >
            {msg.role === "assistant" && (
              <div className="w-8 h-8 rounded-full bg-ink text-white flex items-center justify-center shrink-0 mt-0.5 shadow-sm">
                <Bot className="w-4 h-4" />
              </div>
            )}

            <div
              className={`max-w-2xl rounded-2xl p-4 text-sm font-body leading-relaxed ${
                msg.role === "user"
                  ? "bg-ink text-white rounded-br-none ml-12"
                  : "bg-white border border-border text-ink rounded-bl-none shadow-sm mr-12"
              }`}
            >
              {/* Markdown content with whitespace pre-line */}
              <div className="whitespace-pre-line prose prose-sm max-w-none text-inherit">
                {msg.content}
              </div>

              {/* Render embedded opportunity card if created by this message */}
              {msg.opportunity && (
                <div className="mt-4 pt-3 border-t border-border">
                  <p className="font-heading font-semibold text-xs text-ink/60 mb-2 uppercase tracking-wider flex items-center gap-1">
                    <Layers className="w-3.5 h-3.5" /> Proposed Opportunity
                  </p>
                  <OpportunityCard
                    opportunity={msg.opportunity}
                    onApprove={handleApproveFromChat}
                    onReject={handleRejectFromChat}
                  />
                </div>
              )}
            </div>

            {msg.role === "user" && (
              <div className="w-8 h-8 rounded-full bg-lime text-ink flex items-center justify-center shrink-0 mt-0.5 font-bold text-xs shadow-sm">
                <User className="w-4 h-4" />
              </div>
            )}
          </div>
        ))}

        {/* Dynamic Tool Activity Indicator */}
        {isStreaming && activeTools.length > 0 && (
          <div className="flex items-center gap-2 text-xs text-ink/50 bg-surface/80 p-2.5 rounded-xl border border-border w-fit ml-11 animate-pulse">
            <RefreshCw className="w-3 h-3 animate-spin text-ink" />
            <span>Executing grounded tools: {activeTools.map((t) => t.name).join(", ")}...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Starter Prompts */}
      <div className="pt-2 pb-2 shrink-0">
        <div className="flex items-center gap-2 overflow-x-auto pb-1 text-xs">
          <span className="text-ink/40 font-medium text-[11px] shrink-0">Try:</span>
          {STARTER_PROMPTS.map((prompt, idx) => (
            <button
              key={idx}
              onClick={() => handleSend(prompt)}
              disabled={isStreaming}
              className="shrink-0 bg-surface hover:bg-ink hover:text-white text-ink/70 px-3 py-1.5 rounded-full border border-border transition-colors text-xs"
            >
              {prompt}
            </button>
          ))}
        </div>
      </div>

      {/* Chat Input Bar */}
      <div className="pt-2 border-t border-border shrink-0">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex items-center gap-2"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about sales decline, bundle opportunities, or policy checks..."
            disabled={isStreaming}
            className="flex-1 font-body text-sm text-ink border border-border rounded-xl px-4 py-2.5 bg-white focus:outline-none focus:ring-2 focus:ring-ink/20 disabled:bg-surface"
          />
          <Button
            type="submit"
            variant="primary"
            disabled={!input.trim() || isStreaming}
            className="bg-lime text-ink hover:bg-lime/90 px-4 py-2.5 rounded-xl font-medium flex items-center gap-1.5 shadow-sm"
          >
            <Send className="w-4 h-4" />
            <span>Send</span>
          </Button>
        </form>
        <p className="text-[11px] text-ink/40 mt-1.5 text-center">
          Gemini Proposes · Deterministic Policy Decides · Merchant Approves · n8n Executes
        </p>
      </div>
    </div>
  );
}
