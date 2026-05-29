// Primitive components: icons, sparkline, metric number, glass building blocks

import React, { useEffect, useId, useRef, useState, useMemo } from 'react';

/* ── Icons (inline, minimal Lucide-style) ─────────────────── */
export const Icon = ({ name, size = 16, stroke = 1.6, color = "currentColor" }) => {
  const paths = {
    search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></>,
    flame: <path d="M12 2c1 3 3 4 3 7a3 3 0 0 1-6 0c0-1 .5-2 1-3-2 2-4 4-4 7a6 6 0 0 0 12 0c0-5-3-7-6-11z" />,
    send: <><path d="m22 2-7 20-4-9-9-4z" /><path d="M22 2 11 13" /></>,
    download: <><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><polyline points="12 7 12 12 15 13" /></>,
    chevronRight: <polyline points="9 18 15 12 9 6" />,
    arrowRight: <><line x1="5" y1="12" x2="19" y2="12" /><polyline points="13 6 19 12 13 18" /></>,
    refresh: <><path d="M3 12a9 9 0 0 1 15-6.7L21 8" /><path d="M21 3v5h-5" /><path d="M21 12a9 9 0 0 1-15 6.7L3 16" /><path d="M3 21v-5h5" /></>,
    eye: <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></>,
    image: <><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="9" cy="9" r="1.5" /><polyline points="21 15 16 10 5 21" /></>,
    paperPlane: <><path d="m22 2-7 20-4-9-9-4z" /><path d="M22 2 11 13" /></>,
    sparkle: <><path d="M12 3l1.6 5.4 5.4 1.6-5.4 1.6L12 17l-1.6-5.4L5 10l5.4-1.6z" /><path d="M19 14l.7 2.3 2.3.7-2.3.7L19 20l-.7-2.3L16 17l2.3-.7z" /></>,
    bell: <><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" /></>,
    target: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1.5" /></>,
    doc: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="8" y1="13" x2="16" y2="13" /><line x1="8" y1="17" x2="16" y2="17" /></>,
    globe: <><circle cx="12" cy="12" r="9" /><line x1="3" y1="12" x2="21" y2="12" /><path d="M12 3a14 14 0 0 1 0 18 14 14 0 0 1 0-18" /></>,
    chat: <path d="M3 6a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H8l-5 4z" />,
    trendUp: <><polyline points="3 17 9 11 13 15 21 7" /><polyline points="14 7 21 7 21 14" /></>,
    building: <><path d="M3 21h18" /><path d="M5 21V7l8-4 8 4v14" /><line x1="9" y1="9" x2="9.01" y2="9" /><line x1="15" y1="9" x2="15.01" y2="9" /><line x1="9" y1="13" x2="9.01" y2="13" /><line x1="15" y1="13" x2="15.01" y2="13" /></>,
    gavel: <><path d="m14 13-7.5 7.5a2.121 2.121 0 0 1-3-3L11 10"/><path d="m16 16 6-6"/><path d="m8 8 6-6"/><path d="m9 7 8 8"/><path d="m21 11-8-8"/></>,
    megaphone: <><path d="m3 11 18-5v12L3 14v-3z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/></>,
    bookmark: <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>,
    network: <><rect x="4" y="4" width="6" height="6" rx="1"/><rect x="14" y="4" width="6" height="6" rx="1"/><rect x="4" y="14" width="6" height="6" rx="1"/><rect x="14" y="14" width="6" height="6" rx="1"/></>,
    activity: <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>,
    warn: <><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></>,
    externalLink: <><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></>,
    wave: <><path d="M3 14c2 0 2-3 5-3s3 3 5 3 2-3 5-3 3 3 3 3" /><path d="M3 9c2 0 2-3 5-3s3 3 5 3 2-3 5-3 3 3 3 3" /></>,
    database: <><ellipse cx="12" cy="5" rx="9" ry="3" /><path d="M3 5v6c0 1.7 4 3 9 3s9-1.3 9-3V5" /><path d="M3 11v6c0 1.7 4 3 9 3s9-1.3 9-3v-6" /></>,
    droplet: <path d="M12 2.5 6 9.5a8 8 0 1 0 12 0z" />,
    sparkles: <><path d="M12 2 14 9l7 2-7 2-2 7-2-7-7-2 7-2z" /><path d="M19 16l1 3 3 1-3 1-1 3-1-3-3-1 3-1z" /></>,
  };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
         stroke={color} strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round">
      {paths[name]}
    </svg>
  );
};

/* ── Sparkline (ME-1: collapsed primitive) ─────────────────
   Hard-coded: stroke 1.6px, terminal dot r=2.6, no drop-shadow filter.
   Only the stroke linear gradient is kept.
   `kpi` is the single remaining variant flag — KPI tiles re-enable the
   filled area under the line. All other consumers get stroke-only.
   Draw is gated by IntersectionObserver (mirrors MetricNumber). */
export const Sparkline = React.memo(function Sparkline({
  values,
  width = 200,
  height = 40,
  color = "#a78bfa",
  kpi = false,
}) {
  const ref = useRef(null);
  // useId() is hydration-safe — Math.random() differed SSR vs client and
  // collapsed boss's entire brief subtree on first paint.
  const id = "sg-" + useId().replace(/:/g, "");
  const [drawn, setDrawn] = useState(false);

  const { linePath, fillPath, lastPoint } = useMemo(() => {
    const max = Math.max(...values);
    const min = Math.min(...values);
    const range = max - min || 1;
    const stepX = width / (values.length - 1);
    const points = values.map((v, i) => [
      i * stepX,
      height - 4 - ((v - min) / range) * (height - 8),
    ]);
    const [first, ...rest] = points;
    let d = `M ${first[0].toFixed(2)} ${first[1].toFixed(2)}`;
    rest.forEach((p, i) => {
      const prev = points[i];
      const cx1 = prev[0] + stepX / 2, cy1 = prev[1];
      const cx2 = p[0] - stepX / 2, cy2 = p[1];
      d += ` C ${cx1.toFixed(2)} ${cy1.toFixed(2)}, ${cx2.toFixed(2)} ${cy2.toFixed(2)}, ${p[0].toFixed(2)} ${p[1].toFixed(2)}`;
    });
    const f = d + ` L ${width} ${height} L 0 ${height} Z`;
    return { linePath: d, fillPath: f, lastPoint: points[points.length - 1] };
  }, [values, width, height]);

  useEffect(() => {
    if (!ref.current) return;
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setDrawn(true);
          obs.disconnect();
        }
      },
      { threshold: 0.05, rootMargin: "0px 0px -40px 0px" }
    );
    obs.observe(ref.current);
    return () => obs.disconnect();
  }, []);

  return (
    <svg
      ref={ref}
      width="100%"
      height="100%"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      style={{ display: "block", overflow: "visible" }}
    >
      <defs>
        {kpi && (
          <linearGradient id={id + "-fill"} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.45" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        )}
        <linearGradient id={id + "-stroke"} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor={color} stopOpacity="0.6" />
          <stop offset="100%" stopColor={color} stopOpacity="1" />
        </linearGradient>
      </defs>
      {kpi && (
        <path
          d={fillPath}
          fill={`url(#${id}-fill)`}
          style={{
            opacity: drawn ? 1 : 0,
            transition: "opacity 600ms ease 300ms",
          }}
        />
      )}
      <path
        d={linePath}
        fill="none"
        stroke={`url(#${id}-stroke)`}
        strokeWidth={1.6}
        strokeLinecap="round"
        strokeLinejoin="round"
        style={{
          strokeDasharray: 2000,
          strokeDashoffset: drawn ? 0 : 2000,
          transition: "stroke-dashoffset 1200ms cubic-bezier(0.25, 0.46, 0.45, 0.94)",
        }}
      />
      <circle
        cx={lastPoint[0]}
        cy={lastPoint[1]}
        r="2.6"
        fill={color}
        style={{ opacity: drawn ? 1 : 0, transition: "opacity 400ms ease 1200ms" }}
      />
    </svg>
  );
});

/* ── MetricNumber (ME-2: was Counter) ──────────────────────
   Props: value, format ('int' | 'decimal' | 'percent').
   Intl.NumberFormat used for output. IntersectionObserver-gated.
   Skips animation under prefers-reduced-motion. */
export const MetricNumber = ({ value, format = "int", duration = 1100, className = "" }) => {
  const [val, setVal] = useState(0);
  const [seen, setSeen] = useState(false);
  const ref = useRef(null);

  const reduced = useMemo(
    () =>
      typeof window !== "undefined" &&
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    []
  );

  const formatter = useMemo(() => {
    if (format === "percent") {
      return new Intl.NumberFormat(undefined, {
        style: "percent",
        maximumFractionDigits: 1,
      });
    }
    if (format === "decimal") {
      return new Intl.NumberFormat(undefined, {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
      });
    }
    return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });
  }, [format]);

  useEffect(() => {
    if (!ref.current) return;
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setSeen(true);
          obs.disconnect();
        }
      },
      { threshold: 0.05, rootMargin: "0px 0px -40px 0px" }
    );
    obs.observe(ref.current);
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    if (!seen) return;
    if (reduced) {
      setVal(value);
      return;
    }
    let start = null;
    let raf;
    const tick = (ts) => {
      if (!start) start = ts;
      const t = Math.min((ts - start) / duration, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      setVal(eased * value);
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [seen, value, duration, reduced]);

  const display =
    format === "int" ? formatter.format(Math.round(val)) : formatter.format(val);
  return (
    <span
      ref={ref}
      className={className}
      tabIndex={-1}
      aria-label={formatter.format(value)}
    >
      {display}
    </span>
  );
};

/* ── StanceDot ────────────────────────────────────────────── */
export const StanceDot = ({ stance, size = 8, style = {} }) => {
  const colors = {
    supportive: "#34d399",
    critical: "#fb7185",
    neutral: "#a78bfa",
  };
  const c = colors[stance] || colors.neutral;
  return (
    <span
      style={{
        display: "inline-block",
        width: size,
        height: size,
        borderRadius: "50%",
        background: c,
        boxShadow: `0 0 ${size}px ${c}`,
        flex: "none",
        ...style,
      }}
    />
  );
};

/* ── LanguagePill ─────────────────────────────────────────── */
export const LanguagePill = ({ lang }) => {
  const labels = { telugu: "TE", hindi: "HI", english: "EN", other: "OTH" };
  return (
    <span className={`lang-pill ${lang}`}>
      <span className="pill-dot"></span>
      {labels[lang] || "—"}
    </span>
  );
};

/* ── LiveDot ──────────────────────────────────────────────── */
export const LiveDot = ({ tone = "live" }) => <span className={`live-dot ${tone}`}></span>;

/* ── Countdown (MO-5: real refresh countdown) ──────────── */
export const Countdown = ({ to, bare = false }) => {
  // mounted gate prevents SSR/CSR hydration mismatch — Date.now() differs
  // between server render and client hydration, which would unmount the
  // entire <App> subtree below this component.
  const [mounted, setMounted] = useState(false);
  const [now, setNow] = useState(0);
  const ref = useRef(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    setMounted(true);
    setNow(Date.now());
  }, []);

  useEffect(() => {
    if (!ref.current) return;
    const obs = new IntersectionObserver(
      ([e]) => setVisible(e.isIntersecting),
      { threshold: 0 }
    );
    obs.observe(ref.current);
    return () => obs.disconnect();
  }, [mounted]);

  useEffect(() => {
    if (!visible) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [visible]);

  if (!mounted) {
    // Static placeholder for SSR — same on server and first client render.
    return (
      <span ref={ref} className="countdown" aria-live="polite" suppressHydrationWarning>
        {bare ? "—:—" : "Next refresh in —:—"}
      </span>
    );
  }

  const diff = Math.max(0, to - now);
  const refreshing = diff === 0;
  const mins = Math.floor(diff / 60000);
  const secs = Math.floor((diff % 60000) / 1000);
  const padded = String(secs).padStart(2, "0");

  return (
    <span ref={ref} className="countdown" aria-live="polite">
      {refreshing ? (
        <><LiveDot tone="red" /> Refreshing…</>
      ) : bare ? (
        <>{mins}:{padded}</>
      ) : (
        <>Next refresh in {mins}:{padded}</>
      )}
    </span>
  );
};

/* ── Reveal on scroll wrapper ─────────────────────────────── */
export const Reveal = ({ children, className = "", delay = 0 }) => {
  const ref = useRef(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setTimeout(() => setSeen(true), delay);
          obs.disconnect();
        }
      },
      { threshold: 0.05, rootMargin: "0px 0px -40px 0px" }
    );
    if (ref.current) obs.observe(ref.current);
    return () => obs.disconnect();
  }, [delay]);
  return (
    <div ref={ref} className={`reveal ${seen ? "in" : ""} ${className}`}>
      {children}
    </div>
  );
};

/* ── Section Header ───────────────────────────────────────── */
export const SectionHead = ({ icon, label, subtitle, accent = "#e9c46a" }) => (
  <div className="section-head">
    <div className="eyebrow" style={{ color: accent }}>
      {icon && <Icon name={icon} size={14} stroke={1.8} />}
      <span>{label}</span>
    </div>
    {subtitle && <div className="subtitle">{subtitle}</div>}
  </div>
);

/* ── ImageSlot — empty placeholder until user uploads an image ───── */
export const ImageSlot = ({ src, alt, kind = "rect", id, label, className = "" }) => {
  const innerSize = kind === "avatar" ? 12 : 20;
  return (
    <div className={`img-slot img-slot--${kind} ${className}`.trim()} data-slot-id={id}>
      {src ? (
        <img src={src} alt={alt || ""} />
      ) : (
        <div className="img-slot__empty">
          <Icon name="image" size={innerSize} stroke={1.4} />
          {label && kind !== "avatar" && kind !== "mini" && (
            <span className="img-slot__label">{label}</span>
          )}
        </div>
      )}
    </div>
  );
};

/* ── MethodPopover — methodology transparency tooltip ───────────── */
export const MethodPopover = ({ title, children, placement = "top" }) => {
  const [open, setOpen] = useState(false);
  const [isTouch, setIsTouch] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0, place: placement });
  const triggerRef = useRef(null);

  useEffect(() => {
    if (!open || !triggerRef.current) return;
    const r = triggerRef.current.getBoundingClientRect();
    const pop = { w: 320, h: 180 };
    const vw = window.innerWidth, vh = window.innerHeight;
    // Default: above the icon, centered horizontally on it
    let left = r.left + r.width / 2 - pop.w / 2;
    let top = r.top - pop.h - 8;
    // Flip below if it overflows top edge
    if (top < 8) top = r.bottom + 8;
    // Clamp horizontally
    if (left < 8) left = 8;
    if (left + pop.w > vw - 8) left = vw - pop.w - 8;
    // Clamp vertically as last resort
    if (top + pop.h > vh - 8) top = Math.max(8, vh - pop.h - 8);
    setPos({ top, left, place: placement });
  }, [open, placement]);

  useEffect(() => {
    if (typeof window !== "undefined" && window.matchMedia) {
      setIsTouch(window.matchMedia("(hover: none)").matches);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e) => {
      if (triggerRef.current && !triggerRef.current.contains(e.target)) setOpen(false);
    };
    const onEsc = (e) => { if (e.key === "Escape") setOpen(false); };
    const onScroll = () => setOpen(false);
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onEsc);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onEsc);
      window.removeEventListener("scroll", onScroll);
    };
  }, [open]);

  const triggerProps = isTouch
    ? {}
    : {};

  const wrapperProps = isTouch
    ? { onClick: (e) => { e.stopPropagation(); setOpen((o) => !o); } }
    : {
        onMouseEnter: () => setOpen(true),
        onMouseLeave: () => setOpen(false),
        onClick: (e) => { e.stopPropagation(); setOpen((o) => !o); }
      };

  return (
    <span className="method-trigger" ref={triggerRef} {...wrapperProps}>
      <button type="button" className="method-icon"
              aria-label={`Methodology: ${title}`}
              aria-expanded={open} {...triggerProps}>i</button>
      {open && (
        <div className={`method-popover method-popover--fixed`} role="tooltip"
             style={{ top: pos.top + "px", left: pos.left + "px" }}>
          <div className="method-popover__title">{title}</div>
          <div className="method-popover__body">{children}</div>
        </div>
      )}
    </span>
  );
};

