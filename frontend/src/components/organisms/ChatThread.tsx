import { useEffect, useRef } from "react";
import ChatBubble from "@/components/molecules/ChatBubble";
import type { ChatItem } from "@/components/molecules/ChatBubble";

export default function ChatThread({ items }: { items: ChatItem[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll ke pesan terakhir
  useEffect(() => {
    // Delay 100ms agar rendering elemen selesai sebelum scroll (fix untuk mobile)
    const timeout = setTimeout(() => {
      bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }, 100);
    return () => clearTimeout(timeout);
  }, [items]);

  return (
    // Container Layout:
    // - w-full & mx-auto: Agar konten di tengah
    // - overflow-x-hidden: Mencegah tabel lebar merusak layout mobile
    // - px-4: Padding mobile
    <div
      data-testid="chat-thread"
      className="mx-auto w-full max-w-3xl min-w-0 overflow-x-hidden px-4 md:px-0"
    >
      <div className="flex flex-col gap-6 md:gap-8">
        {/* Date Badge */}
        <div className="pointer-events-none sticky top-0 z-10 flex justify-center py-6">
          <span className="inline-flex items-center rounded-full border border-zinc-200/50 bg-white/60 px-4 py-1.5 text-[10px] font-bold uppercase tracking-widest text-zinc-500 backdrop-blur-xl shadow-sm">
            {new Date().toLocaleDateString("id-ID", {
              weekday: "long",
              day: "numeric",
              month: "short",
            })}
          </span>
        </div>

        {/* ✅ Pembaruan kompatibilitas:
            ChatItem sekarang boleh punya `sources?: [...]`.
            ChatBubble sudah handle itu, jadi di sini tidak perlu ubah desain/markup. */}
        {items.map((it) => (
          <ChatBubble key={it.id} item={it} />
        ))}

        {/* Dummy element scroll target */}
        <div ref={bottomRef} className="h-px w-full mt-2" />
      </div>
    </div>
  );
}
