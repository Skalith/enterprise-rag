"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, History, Plus, SlidersHorizontal, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { chatApi } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/client";
import { qk, useConversation, useConversations } from "@/lib/api/queries";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { DropdownContent, DropdownMenu, DropdownTrigger } from "@/components/ui/dropdown";
import { SourcesButton, SourcesDrawer } from "@/components/chat/sources";
import { cn, formatMs, formatRelative } from "@/lib/utils";
import type { ChatSource, Message } from "@/lib/types";

const CITE_SUFFIX = "\n\n(Please cite sources.)";
const stripCite = (s: string) => (s.endsWith(CITE_SUFFIX) ? s.slice(0, -CITE_SUFFIX.length) : s);

interface ThreadMessage {
  key: string;
  role: "user" | "assistant";
  content: string;
  sources: ChatSource[];
  meta?: string;
  pending?: boolean;
  failed?: boolean;
}

const fromServer = (m: Message): ThreadMessage => ({
  key: `m${m.id}`,
  role: m.role === "assistant" ? "assistant" : "user",
  content: m.role === "assistant" ? m.content : stripCite(m.content),
  sources: m.sources ?? [],
  meta:
    m.role === "assistant"
      ? [m.token_usage?.model, m.latency_ms != null ? formatMs(m.latency_ms) : null].filter(Boolean).join(" · ")
      : undefined,
});

function ConversationList({ activeId, onSelect, onNew }: { activeId: number | null; onSelect: (id: number) => void; onNew: () => void }) {
  const convs = useConversations();
  return (
    <div className="flex h-full flex-col">
      <div className="p-3">
        <Button variant="secondary" className="w-full justify-start" onClick={onNew}>
          <Plus className="h-4 w-4" /> New chat
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {convs.isLoading ? (
          <div className="space-y-2 p-1">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-11" />)}</div>
        ) : convs.isError ? (
          <ErrorState error={convs.error} onRetry={() => convs.refetch()} className="py-8" />
        ) : (convs.data ?? []).length === 0 ? (
          <p className="px-3 py-6 text-center text-[13px] text-muted">Your conversations will appear here.</p>
        ) : (
          <ul className="space-y-0.5">
            {convs.data!.map((c) => (
              <li key={c.id}>
                <button
                  onClick={() => onSelect(c.id)}
                  aria-current={c.id === activeId ? "true" : undefined}
                  className={cn(
                    "w-full rounded-md px-3 py-2 text-left transition-colors",
                    c.id === activeId ? "bg-accent-soft" : "hover:bg-sunken",
                  )}
                >
                  <span className={cn("block truncate text-[13px] font-medium", c.id === activeId ? "text-accent" : "text-ink")}>{c.title}</span>
                  <span className="block text-xs text-muted">{formatRelative(c.created_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function TypingDots() {
  return (
    <span className="inline-flex gap-1 py-1" role="status" aria-label="Assistant is thinking">
      {[0, 1, 2].map((i) => (
        <span key={i} className="h-1.5 w-1.5 rounded-full bg-subtle" style={{ animation: `dot 1.2s ${i * 0.15}s infinite` }} />
      ))}
    </span>
  );
}

function ChatInner() {
  const router = useRouter();
  const params = useSearchParams();
  const qc = useQueryClient();

  const urlId = params.get("c") ? Number(params.get("c")) : null;
  const [activeId, setActiveId] = useState<number | null>(urlId);
  const [thread, setThread] = useState<ThreadMessage[]>([]);
  const [input, setInput] = useState("");
  const [askSources, setAskSources] = useState(false);
  const [topK, setTopK] = useState(5);
  const [drawer, setDrawer] = useState<ChatSource[] | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const skipLoad = useRef<number | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  const detail = useConversation(activeId);

  // Load a conversation selected from history / URL (not one we just created locally).
  useEffect(() => {
    if (activeId == null) {
      setThread([]);
      return;
    }
    if (skipLoad.current === activeId) return;
    if (detail.data) setThread(detail.data.messages.filter((m) => m.role !== "system").map(fromServer));
  }, [activeId, detail.data]);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [thread]);

  const select = useCallback(
    (id: number | null) => {
      skipLoad.current = null;
      setActiveId(id);
      setHistoryOpen(false);
      router.replace(id ? `/chat?c=${id}` : "/chat");
    },
    [router],
  );

  const send = useMutation({
    mutationFn: (question: string) => chatApi.send({ question, conversation_id: activeId, top_k: topK }),
    onSuccess: (res) => {
      skipLoad.current = res.conversation_id;
      setThread((t) => [
        ...t.filter((m) => !m.pending),
        {
          key: `m${res.message_id}`,
          role: "assistant",
          content: res.answer,
          sources: res.sources ?? [],
          meta: formatMs(res.latency_ms),
        },
      ]);
      if (activeId !== res.conversation_id) {
        setActiveId(res.conversation_id);
        router.replace(`/chat?c=${res.conversation_id}`);
      }
      qc.invalidateQueries({ queryKey: qk.conversations });
      qc.invalidateQueries({ queryKey: qk.conversation(res.conversation_id) });
    },
    onError: (e: Error) => {
      const msg =
        e instanceof ApiError && e.isRateLimited
          ? `Chat is rate limited. Try again${e.retryAfter ? ` in ${e.retryAfter}s` : " in a moment"}.`
          : e.message;
      setThread((t) => [...t.filter((m) => !m.pending), { key: `err${Date.now()}`, role: "assistant", content: msg, sources: [], failed: true }]);
      toast.error("Message not sent", { description: msg });
    },
  });

  function submit() {
    const text = input.trim();
    if (!text || send.isPending) return;
    if (text.length > 2000) return toast.error("Questions can be up to 2,000 characters.");
    const wire = askSources ? text + CITE_SUFFIX : text;
    setThread((t) => [
      ...t,
      { key: `u${Date.now()}`, role: "user", content: text, sources: [] },
      { key: `p${Date.now()}`, role: "assistant", content: "", sources: [], pending: true },
    ]);
    setInput("");
    taRef.current?.focus();
    send.mutate(wire.length > 2000 ? text : wire);
  }

  const empty = thread.length === 0 && !(activeId && detail.isLoading);

  return (
    <div className="flex h-[calc(100dvh-3.5rem)] min-h-0">
      <aside className="hidden w-72 shrink-0 border-r border-line bg-surface md:block">
        <ConversationList activeId={activeId} onSelect={select} onNew={() => select(null)} />
      </aside>

      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-2 md:hidden">
          <Button variant="ghost" size="sm" onClick={() => setHistoryOpen(true)}>
            <History className="h-4 w-4" /> History
          </Button>
          <Button variant="ghost" size="sm" onClick={() => select(null)}>
            <Plus className="h-4 w-4" /> New
          </Button>
        </div>

        <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6">
            {activeId && detail.isLoading && thread.length === 0 ? (
              <div className="space-y-6">{[0, 1].map((i) => <Skeleton key={i} className="h-24" />)}</div>
            ) : activeId && detail.isError && thread.length === 0 ? (
              <ErrorState error={detail.error} onRetry={() => detail.refetch()} title="Could not open this conversation" />
            ) : empty ? (
              <EmptyState
                className="py-24"
                icon={<Sparkles className="h-5 w-5" />}
                title="Ask about your documents"
                description="Answers come only from documents you are allowed to see. Turn on “Ask for sources” to see the passages used."
              />
            ) : (
              <ol className="space-y-8">
                {thread.map((m) =>
                  m.role === "user" ? (
                    <li key={m.key} className="flex justify-end">
                      <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-accent px-4 py-2.5 text-[14px] text-accent-fg">
                        {m.content}
                      </p>
                    </li>
                  ) : (
                    <li key={m.key} className="max-w-[92%]">
                      {m.pending ? (
                        <TypingDots />
                      ) : (
                        <>
                          <p
                            className={cn(
                              "whitespace-pre-wrap font-serif text-[16px] leading-[1.7]",
                              m.failed ? "text-danger" : "text-ink",
                            )}
                            role={m.failed ? "alert" : undefined}
                          >
                            {m.content}
                          </p>
                          <div className="mt-2.5 flex flex-wrap items-center gap-3">
                            {m.sources.length > 0 && <SourcesButton sources={m.sources} onOpen={() => setDrawer(m.sources)} />}
                            {m.meta && <span className="text-xs text-subtle">{m.meta}</span>}
                          </div>
                        </>
                      )}
                    </li>
                  ),
                )}
              </ol>
            )}
          </div>
        </div>

        <div className="border-t border-line bg-surface px-4 py-3 sm:px-6">
          <div className="mx-auto max-w-3xl">
            <div className="flex items-end gap-2 rounded-xl border border-line-strong bg-paper p-2 focus-within:border-accent">
              <textarea
                ref={taRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    submit();
                  }
                }}
                rows={1}
                maxLength={2000}
                placeholder="Ask a question about your documents…"
                aria-label="Your question"
                className="max-h-40 min-h-[40px] flex-1 resize-none bg-transparent px-2 py-2 text-[14px] text-ink outline-none placeholder:text-subtle"
                style={{ fieldSizing: "content" } as React.CSSProperties}
              />
              <DropdownMenu>
                <DropdownTrigger asChild>
                  <Button variant="ghost" size="icon" aria-label="Chat settings">
                    <SlidersHorizontal className="h-4 w-4" />
                  </Button>
                </DropdownTrigger>
                <DropdownContent align="end" className="w-64 p-3">
                  <label className="flex items-center justify-between gap-3 text-[13px] text-ink">
                    Ask for sources
                    <Switch checked={askSources} onCheckedChange={setAskSources} aria-label="Ask for sources" />
                  </label>
                  <p className="mt-1.5 text-xs text-muted">The assistant only returns source passages when the question asks for them.</p>
                  <div className="mt-4">
                    <label htmlFor="topk" className="flex justify-between text-[13px] text-ink">
                      Passages to retrieve <span className="tabular text-muted">{topK}</span>
                    </label>
                    <input
                      id="topk"
                      type="range"
                      min={1}
                      max={20}
                      value={topK}
                      onChange={(e) => setTopK(Number(e.target.value))}
                      className="mt-2 w-full accent-[var(--accent)]"
                    />
                  </div>
                </DropdownContent>
              </DropdownMenu>
              <Button size="icon" onClick={submit} disabled={!input.trim() || send.isPending} aria-label="Send question">
                <ArrowUp className="h-4 w-4" />
              </Button>
            </div>
            <p className="mt-1.5 flex justify-between px-1 text-xs text-subtle">
              <span>{askSources ? "Sources on" : "Enter to send · Shift+Enter for a new line"}</span>
              <span className="tabular">{input.length}/2000</span>
            </p>
          </div>
        </div>
      </section>

      <SourcesDrawer sources={drawer ?? []} open={!!drawer} onOpenChange={(o) => !o && setDrawer(null)} />
      <Dialog open={historyOpen} onOpenChange={setHistoryOpen}>
        <DialogContent title="Conversations" side="left">
          <ConversationList activeId={activeId} onSelect={select} onNew={() => select(null)} />
        </DialogContent>
      </Dialog>
      
    </div>
  );
}

export default function ChatPage() {
  return (
    <Suspense fallback={null}>
      <ChatInner />
    </Suspense>
  );
}
