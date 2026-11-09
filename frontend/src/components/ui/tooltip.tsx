"use client";

import * as React from "react";
import * as TT from "@radix-ui/react-tooltip";

export const TooltipProvider = TT.Provider;

export function Tooltip({
  content,
  children,
  side = "right",
  disabled,
}: {
  content: React.ReactNode;
  children: React.ReactNode;
  side?: "top" | "right" | "bottom" | "left";
  disabled?: boolean;
}) {
  if (disabled) return <>{children}</>;
  return (
    <TT.Root delayDuration={150}>
      <TT.Trigger asChild>{children}</TT.Trigger>
      <TT.Portal>
        <TT.Content
          side={side}
          sideOffset={8}
          className="anim-fade z-[60] max-w-xs rounded-md bg-ink px-2.5 py-1.5 text-xs text-paper shadow-pop"
        >
          {content}
        </TT.Content>
      </TT.Portal>
    </TT.Root>
  );
}
