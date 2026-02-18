import { cn } from "@/lib/utils";

export default function Avatar({
  imageUrl,
  className,
}: {
  imageUrl?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "size-9 rounded-full bg-cover bg-center border border-black/10 grayscale hover:grayscale-0",
        "transition-all duration-500 cursor-pointer",
        className
      )}
      style={imageUrl ? { backgroundImage: `url('${imageUrl}')` } : undefined}
    />
  );
}
