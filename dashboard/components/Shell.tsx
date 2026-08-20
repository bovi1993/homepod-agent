"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Camera,
  Home as HomeIcon,
  MessageCircle,
  Settings,
  type LucideIcon,
} from "lucide-react";
import { clsx } from "clsx";

const NAV: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/", label: "Home", icon: HomeIcon },
  { href: "/chat", label: "Chat", icon: MessageCircle },
  { href: "/cameras", label: "Cameras", icon: Camera },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Shell({
  children,
  title,
  subtitle,
  right,
}: {
  children: React.ReactNode;
  title?: string;
  subtitle?: React.ReactNode;
  right?: React.ReactNode;
}) {
  const pathname = usePathname();

  return (
    <div className="mx-auto flex min-h-dvh max-w-home flex-col px-4 pb-24 pt-6 sm:px-6 sm:pb-10 sm:pt-8">
      <header className="mb-6 flex items-start justify-between gap-4">
        <div className="min-w-0">
          {title ? (
            <>
              <p className="text-micro font-medium uppercase tracking-wider text-fg-faint">
                homepod-agent
              </p>
              <h1 className="truncate text-2xl font-semibold tracking-tight text-fg sm:text-[1.75rem]">
                {title}
              </h1>
              {subtitle && (
                <div className="mt-1 text-sm text-fg-muted">{subtitle}</div>
              )}
            </>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {right}
          {/* Desktop top nav */}
          <nav className="hidden items-center gap-1 rounded-full border border-white/[0.08] bg-white/[0.03] p-1 sm:flex">
            {NAV.map(({ href, label, icon: Icon }) => {
              const active =
                href === "/" ? pathname === "/" : pathname.startsWith(href);
              return (
                <Link
                  key={href}
                  href={href}
                  className={clsx(
                    "flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[13px] font-medium transition",
                    active
                      ? "bg-white/[0.08] text-fg"
                      : "text-fg-muted hover:bg-white/[0.04] hover:text-fg-secondary"
                  )}
                >
                  <Icon size={14} strokeWidth={2} />
                  {label}
                </Link>
              );
            })}
          </nav>
        </div>
      </header>

      <div className="flex-1">{children}</div>

      {/* Mobile bottom nav */}
      <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-white/[0.06] bg-bg/90 backdrop-blur-xl safe-pb sm:hidden">
        <ul className="mx-auto flex max-w-home items-stretch justify-around px-2 pt-1">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active =
              href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <li key={href} className="flex-1">
                <Link
                  href={href}
                  className={clsx(
                    "flex flex-col items-center gap-0.5 py-2 text-[11px] font-medium",
                    active ? "text-accent" : "text-fg-faint"
                  )}
                >
                  <Icon size={20} strokeWidth={active ? 2.25 : 1.75} />
                  {label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}

export function Pill({
  ok,
  label,
  detail,
}: {
  ok?: boolean | null;
  label: string;
  detail?: string;
}) {
  const tone =
    ok === true ? "bg-success" : ok === false ? "bg-danger" : "bg-fg-faint";
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-white/[0.08] bg-white/[0.03] px-2.5 py-1 text-[12px] text-fg-secondary">
      <span className={clsx("h-1.5 w-1.5 rounded-full", tone)} />
      <span className="font-medium">{label}</span>
      {detail && <span className="text-fg-faint">{detail}</span>}
    </span>
  );
}

export function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-3 text-[13px] font-medium uppercase tracking-wider text-fg-faint">
      {children}
    </h2>
  );
}
