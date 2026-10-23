"use client";

import { useId } from "react";

import { cn } from "@/lib/cn";

/** The TokenShield mark: a shield with a token slot cut through it. */
export function ShieldMark({ className }: { className?: string }) {
  // A unique gradient id per instance: when the first SVG defining a shared id sits in a
  // hidden subtree (the collapsed sidebar on phones), browsers resolve the fill to nothing.
  const gradient = `ts-mark-${useId().replace(/:/g, "")}`;
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cn("size-7 shrink-0", className)}>
      <defs>
        <linearGradient id={gradient} x1="6" y1="3" x2="26" y2="29" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="var(--chart-spend)" />
          <stop offset="1" stopColor="var(--primary)" />
        </linearGradient>
      </defs>
      <path
        d="M16 2.5 4.5 6.8v8.3c0 7.1 4.8 12.6 11.5 14.4 6.7-1.8 11.5-7.3 11.5-14.4V6.8L16 2.5Z"
        fill={`url(#${gradient})`}
      />
      <path
        d="M16 5.6 7.5 8.8v6.3c0 5.4 3.5 9.7 8.5 11.3"
        fill="none"
        stroke="white"
        strokeOpacity="0.28"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
      <rect x="10.5" y="13.2" width="11" height="3.6" rx="1.8" fill="white" />
      <circle cx="16" cy="21.2" r="1.7" fill="white" fillOpacity="0.85" />
    </svg>
  );
}

export function ShieldLogo({ className, collapsed = false }: { className?: string; collapsed?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <ShieldMark />
      {!collapsed && <span className="text-[15px] font-semibold tracking-[-0.02em] text-foreground">TokenShield</span>}
    </span>
  );
}
