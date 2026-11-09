"use client";

import * as React from "react";
import * as DM from "@radix-ui/react-dropdown-menu";
import { cn } from "@/lib/utils";

export const DropdownMenu = DM.Root;
export const DropdownTrigger = DM.Trigger;

export function DropdownContent({ className, align = "end", ...props }: React.ComponentProps<typeof DM.Content>) {
  return (
    <DM.Portal>
      <DM.Content
        align={align}
        sideOffset={6}
        className={cn(
          "anim-pop z-50 min-w-[11rem] rounded-lg border border-line bg-surface p-1 shadow-pop",
          className,
        )}
        {...props}
      />
    </DM.Portal>
  );
}

export function DropdownItem({
  className,
  danger,
  ...props
}: React.ComponentProps<typeof DM.Item> & { danger?: boolean }) {
  return (
    <DM.Item
      className={cn(
        "flex cursor-pointer select-none items-center gap-2 rounded-md px-2.5 py-1.5 text-[13px] outline-none data-[disabled]:pointer-events-none data-[disabled]:opacity-45",
        danger ? "text-danger data-[highlighted]:bg-danger-soft" : "text-ink data-[highlighted]:bg-sunken",
        className,
      )}
      {...props}
    />
  );
}

export const DropdownLabel = ({ className, ...props }: React.ComponentProps<typeof DM.Label>) => (
  <DM.Label className={cn("px-2.5 py-1.5 text-xs text-muted", className)} {...props} />
);
export const DropdownSeparator = ({ className, ...props }: React.ComponentProps<typeof DM.Separator>) => (
  <DM.Separator className={cn("my-1 h-px bg-line", className)} {...props} />
);
