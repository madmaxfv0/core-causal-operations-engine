/**
 * Floating-overlay primitives.
 *
 * Every hover card, tooltip, popover and dropdown in CORE renders through these
 * components.  They exist to solve one concrete class of bug: a floating element
 * declared inside a card, a scrolling table, a drawer or the map container is
 * clipped by that ancestor's `overflow`, or trapped underneath a later sibling
 * because the ancestor created a stacking context (`transform`, `filter`,
 * `backdrop-filter`, `isolation`, `position` + `z-index`).
 *
 * The fix has three parts and all three are required:
 *
 *  1. PORTAL - the element is rendered into `document.body`, so no ancestor's
 *     `overflow: hidden/auto` can clip it and no ancestor stacking context can
 *     trap it.  A large `z-index` alone cannot escape a stacking context.
 *  2. FIXED POSITIONING - `position: fixed` measured against the trigger's
 *     viewport rect, so the overlay follows the trigger without inheriting a
 *     transformed containing block.
 *  3. COLLISION HANDLING - flip to the opposite side when the preferred side has
 *     no room, then shift along the cross axis so the whole card stays inside the
 *     viewport.  The overlay is never allowed to run off screen.
 *
 * Layer order is centralised in `LAYER` (mirrors the --z-* custom properties in
 * index.css) instead of ad-hoc `z-[99999]` values.
 */
import React, { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { useT } from "../lib/i18n";
import { createPortal } from "react-dom";

export const LAYER = {
  base: 0,
  sticky: 20,
  mapControls: 100,
  drawer: 300,
  dropdown: 500,
  popover: 600,
  tooltip: 700,
  modal: 800,
  toast: 900,
} as const;

export type Side = "top" | "bottom" | "left" | "right";
type Rect = { top: number; left: number; width: number; height: number };

const MARGIN = 8;      // minimum gap from the viewport edge
const GAP = 8;         // gap between trigger and overlay

function place(anchor: Rect, size: { width: number; height: number }, side: Side, align: "start" | "center" | "end") {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const room = {
    top: anchor.top - MARGIN,
    bottom: vh - (anchor.top + anchor.height) - MARGIN,
    left: anchor.left - MARGIN,
    right: vw - (anchor.left + anchor.width) - MARGIN,
  };
  const need = side === "top" || side === "bottom" ? size.height + GAP : size.width + GAP;
  const opposite: Record<Side, Side> = { top: "bottom", bottom: "top", left: "right", right: "left" };
  // flip when the preferred side cannot fit but the opposite one can
  let used: Side = side;
  if (room[side] < need && room[opposite[side]] > room[side]) used = opposite[side];

  let top: number;
  let left: number;
  if (used === "top" || used === "bottom") {
    top = used === "top" ? anchor.top - size.height - GAP : anchor.top + anchor.height + GAP;
    left = align === "start" ? anchor.left
      : align === "end" ? anchor.left + anchor.width - size.width
      : anchor.left + anchor.width / 2 - size.width / 2;
  } else {
    left = used === "left" ? anchor.left - size.width - GAP : anchor.left + anchor.width + GAP;
    top = align === "start" ? anchor.top
      : align === "end" ? anchor.top + anchor.height - size.height
      : anchor.top + anchor.height / 2 - size.height / 2;
  }
  // shift back inside the viewport on both axes
  left = Math.min(Math.max(MARGIN, left), Math.max(MARGIN, vw - size.width - MARGIN));
  top = Math.min(Math.max(MARGIN, top), Math.max(MARGIN, vh - size.height - MARGIN));
  return { top, left, side: used };
}

export function useAnchorRect(open: boolean) {
  const ref = useRef<HTMLElement | null>(null);
  const [rect, setRect] = useState<Rect | null>(null);
  const measure = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    setRect({ top: r.top, left: r.left, width: r.width, height: r.height });
  }, []);
  useLayoutEffect(() => {
    if (!open) return;
    measure();
    const handler = () => measure();
    window.addEventListener("scroll", handler, true);
    window.addEventListener("resize", handler);
    return () => { window.removeEventListener("scroll", handler, true); window.removeEventListener("resize", handler); };
  }, [open, measure]);
  return { ref, rect, measure };
}

/** Portal + fixed + collision-aware container. Anything floating goes through here. */
export function Floating({
  anchor, open, side = "bottom", align = "center", layer = LAYER.popover,
  className = "", style, children, onPointerEnter, onPointerLeave, role = "dialog", interactive = true,
}: {
  anchor: Rect | null; open: boolean; side?: Side; align?: "start" | "center" | "end";
  layer?: number; className?: string; style?: React.CSSProperties; children: React.ReactNode;
  onPointerEnter?: () => void; onPointerLeave?: () => void; role?: string; interactive?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  useLayoutEffect(() => {
    if (!open || !anchor || !ref.current) { setPos(null); return; }
    const box = ref.current.getBoundingClientRect();
    setPos(place(anchor, { width: box.width, height: box.height }, side, align));
  }, [open, anchor, side, align, children]);
  if (!open || !anchor || typeof document === "undefined") return null;
  return createPortal(
    <div
      ref={ref}
      role={role}
      onPointerEnter={onPointerEnter}
      onPointerLeave={onPointerLeave}
      className={`fade-in ${className}`}
      style={{
        position: "fixed",
        zIndex: layer,
        top: pos ? pos.top : anchor.top + anchor.height + GAP,
        left: pos ? pos.left : anchor.left,
        maxWidth: `calc(100vw - ${MARGIN * 2}px)`,
        maxHeight: `calc(100vh - ${MARGIN * 2}px)`,
        pointerEvents: interactive ? "auto" : "none",
        visibility: pos ? "visible" : "hidden",
        ...style,
      }}
    >
      {children}
    </div>,
    document.body,
  );
}

/**
 * Hover shows a preview, click pins it open.
 * Pinned cards survive the pointer leaving, so the content can be read and copied.
 * On touch devices (no hover) the first tap pins directly.
 */
export function HoverCard({
  children, content, side = "top", align = "center", width = 320, layer = LAYER.popover,
  openDelay = 90, closeDelay = 140, className = "", pinnable = true, label,
}: {
  children: React.ReactNode; content: React.ReactNode; side?: Side; align?: "start" | "center" | "end";
  width?: number | string; layer?: number; openDelay?: number; closeDelay?: number;
  className?: string; pinnable?: boolean; label?: string;
}) {
  const [hovered, setHovered] = useState(false);
  const [pinned, setPinned] = useState(false);
  const open = hovered || pinned;
  const { ref, rect, measure } = useAnchorRect(open);
  const { t } = useT();
  const timer = useRef<number | undefined>(undefined);
  const id = useId();
  const schedule = (value: boolean, delay: number) => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => { measure(); setHovered(value); }, delay);
  };
  useEffect(() => () => window.clearTimeout(timer.current), []);
  useEffect(() => {
    if (!pinned) return;
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") setPinned(false); };
    const down = (e: MouseEvent) => {
      const target = e.target as Node;
      if (ref.current?.contains(target)) return;
      if ((target as HTMLElement)?.closest?.(`[data-hovercard="${id}"]`)) return;
      setPinned(false);
    };
    document.addEventListener("keydown", key);
    document.addEventListener("mousedown", down);
    return () => { document.removeEventListener("keydown", key); document.removeEventListener("mousedown", down); };
  }, [pinned, id, ref]);
  return (
    <>
      <span
        ref={ref as React.RefObject<HTMLSpanElement>}
        className={`inline-flex items-center ${pinnable ? "cursor-pointer" : ""} ${className}`}
        tabIndex={0}
        aria-label={label}
        aria-expanded={open}
        onPointerEnter={(e) => { if (e.pointerType !== "touch") schedule(true, openDelay); }}
        onPointerLeave={(e) => { if (e.pointerType !== "touch") schedule(false, closeDelay); }}
        onFocus={() => { measure(); setHovered(true); }}
        onBlur={() => setHovered(false)}
        onClick={() => { if (pinnable) { measure(); setPinned((p) => !p); } }}
        onKeyDown={(e) => { if (pinnable && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); measure(); setPinned((p) => !p); } }}
      >
        {children}
      </span>
      <Floating
        anchor={rect} open={open} side={side} align={align} layer={pinned ? layer + 20 : layer}
        onPointerEnter={() => window.clearTimeout(timer.current)}
        onPointerLeave={() => schedule(false, closeDelay)}
        className="glass-strong p-3 text-[12px] overflow-auto"
        style={{ width, boxShadow: "0 24px 70px rgba(0,0,0,0.55)" }}
      >
        <div data-hovercard={id}>
          {pinnable && (
            <div className="flex items-center justify-between gap-3 mb-2">
              <span className="faint text-[10px] uppercase tracking-wide">{pinned ? t("hc_pinned") : t("hc_pin")}</span>
              {pinned && <button className="btn ghost sm" style={{ padding: "1px 6px" }} onClick={() => setPinned(false)} aria-label={t("x_close")}>✕</button>}
            </div>
          )}
          {content}
        </div>
      </Floating>
    </>
  );
}

/** Small non-interactive label tooltip; never clipped, never off-screen. */
export function Tip({ children, label, side = "top" }: { children: React.ReactNode; label: React.ReactNode; side?: Side }) {
  const [open, setOpen] = useState(false);
  const { ref, rect, measure } = useAnchorRect(open);
  return (
    <>
      <span
        ref={ref as React.RefObject<HTMLSpanElement>}
        className="inline-flex items-center"
        onPointerEnter={() => { measure(); setOpen(true); }}
        onPointerLeave={() => setOpen(false)}
        onFocus={() => { measure(); setOpen(true); }}
        onBlur={() => setOpen(false)}
        tabIndex={0}
      >
        {children}
      </span>
      <Floating
        anchor={rect} open={open} side={side} layer={LAYER.tooltip} role="tooltip" interactive={false}
        className="glass-strong px-2.5 py-1.5 text-[12px]"
        style={{ borderRadius: 10, maxWidth: 300 }}
      >
        {label}
      </Floating>
    </>
  );
}

/** Anchored dropdown (search results, menus) that escapes scrolling ancestors. */
export function Dropdown({
  open, onClose, anchorRef, children, width, align = "start", layer = LAYER.dropdown,
}: {
  open: boolean; onClose: () => void; anchorRef: React.RefObject<HTMLElement | null>;
  children: React.ReactNode; width?: number | string; align?: "start" | "center" | "end"; layer?: number;
}) {
  const [rect, setRect] = useState<Rect | null>(null);
  useLayoutEffect(() => {
    if (!open || !anchorRef.current) return;
    const measure = () => {
      const el = anchorRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      setRect({ top: r.top, left: r.left, width: r.width, height: r.height });
    };
    measure();
    window.addEventListener("scroll", measure, true);
    window.addEventListener("resize", measure);
    return () => { window.removeEventListener("scroll", measure, true); window.removeEventListener("resize", measure); };
  }, [open, anchorRef]);
  useEffect(() => {
    if (!open) return;
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [open, onClose]);
  return (
    <Floating anchor={rect} open={open} side="bottom" align={align} layer={layer}
      className="glass-strong p-2 overflow-auto" style={{ width: width ?? rect?.width, maxHeight: 380 }} role="listbox">
      {children}
    </Floating>
  );
}
