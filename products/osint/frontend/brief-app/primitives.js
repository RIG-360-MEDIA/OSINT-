/* compiled from primitives.jsx — do not edit directly */
(function(){
/* global React, window */
// Primitive components: icons, sparkline, glass building blocks

const {
  useEffect,
  useRef,
  useState,
  useMemo
} = React;

/* ── Icons (inline, minimal Lucide-style) ─────────────────── */
const Icon = ({
  name,
  size = 16,
  stroke = 1.6,
  color = "currentColor"
}) => {
  const paths = {
    search: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("circle", {
      cx: "11",
      cy: "11",
      r: "7"
    }), /*#__PURE__*/React.createElement("path", {
      d: "m20 20-3.5-3.5"
    })),
    flame: /*#__PURE__*/React.createElement("path", {
      d: "M12 2c1 3 3 4 3 7a3 3 0 0 1-6 0c0-1 .5-2 1-3-2 2-4 4-4 7a6 6 0 0 0 12 0c0-5-3-7-6-11z"
    }),
    send: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "m22 2-7 20-4-9-9-4z"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M22 2 11 13"
    })),
    download: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"
    }), /*#__PURE__*/React.createElement("polyline", {
      points: "7 10 12 15 17 10"
    }), /*#__PURE__*/React.createElement("line", {
      x1: "12",
      y1: "15",
      x2: "12",
      y2: "3"
    })),
    clock: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("circle", {
      cx: "12",
      cy: "12",
      r: "9"
    }), /*#__PURE__*/React.createElement("polyline", {
      points: "12 7 12 12 15 13"
    })),
    chevronRight: /*#__PURE__*/React.createElement("polyline", {
      points: "9 18 15 12 9 6"
    }),
    arrowRight: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("line", {
      x1: "5",
      y1: "12",
      x2: "19",
      y2: "12"
    }), /*#__PURE__*/React.createElement("polyline", {
      points: "13 6 19 12 13 18"
    })),
    refresh: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "M3 12a9 9 0 0 1 15-6.7L21 8"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M21 3v5h-5"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M21 12a9 9 0 0 1-15 6.7L3 16"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M3 21v-5h5"
    })),
    eye: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"
    }), /*#__PURE__*/React.createElement("circle", {
      cx: "12",
      cy: "12",
      r: "3"
    })),
    image: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("rect", {
      x: "3",
      y: "3",
      width: "18",
      height: "18",
      rx: "2"
    }), /*#__PURE__*/React.createElement("circle", {
      cx: "9",
      cy: "9",
      r: "1.5"
    }), /*#__PURE__*/React.createElement("polyline", {
      points: "21 15 16 10 5 21"
    })),
    paperPlane: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "m22 2-7 20-4-9-9-4z"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M22 2 11 13"
    })),
    wave: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "M3 14c2 0 2-3 5-3s3 3 5 3 2-3 5-3 3 3 3 3"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M3 9c2 0 2-3 5-3s3 3 5 3 2-3 5-3 3 3 3 3"
    })),
    database: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("ellipse", {
      cx: "12",
      cy: "5",
      rx: "9",
      ry: "3"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M3 5v6c0 1.7 4 3 9 3s9-1.3 9-3V5"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M3 11v6c0 1.7 4 3 9 3s9-1.3 9-3v-6"
    })),
    droplet: /*#__PURE__*/React.createElement("path", {
      d: "M12 2.5 6 9.5a8 8 0 1 0 12 0z"
    }),
    sparkles: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "M12 2 14 9l7 2-7 2-2 7-2-7-7-2 7-2z"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M19 16l1 3 3 1-3 1-1 3-1-3-3-1 3-1z"
    }))
  };
  return /*#__PURE__*/React.createElement("svg", {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: color,
    strokeWidth: stroke,
    strokeLinecap: "round",
    strokeLinejoin: "round"
  }, paths[name]);
};

/* ── Sparkline ────────────────────────────────────────────── */
const Sparkline = React.memo(function Sparkline({
  values,
  width = 200,
  height = 40,
  color = "#a78bfa",
  gradient = true,
  fill = true,
  delay = 0,
  thick = false,
  showDot = true
}) {
  const pathRef = useRef(null);
  const id = useMemo(() => "sg-" + Math.random().toString(36).slice(2, 9), []);
  const [drawn, setDrawn] = useState(false);

  // Heavy path math — memoized so re-renders are cheap
  const {
    linePath,
    fillPath,
    lastPoint
  } = useMemo(() => {
    const max = Math.max(...values);
    const min = Math.min(...values);
    const range = max - min || 1;
    const stepX = width / (values.length - 1);
    const points = values.map((v, i) => [i * stepX, height - 4 - (v - min) / range * (height - 8)]);
    const [first, ...rest] = points;
    let d = `M ${first[0].toFixed(2)} ${first[1].toFixed(2)}`;
    rest.forEach((p, i) => {
      const prev = points[i];
      const cx1 = prev[0] + stepX / 2,
        cy1 = prev[1];
      const cx2 = p[0] - stepX / 2,
        cy2 = p[1];
      d += ` C ${cx1.toFixed(2)} ${cy1.toFixed(2)}, ${cx2.toFixed(2)} ${cy2.toFixed(2)}, ${p[0].toFixed(2)} ${p[1].toFixed(2)}`;
    });
    const fill = d + ` L ${width} ${height} L 0 ${height} Z`;
    return {
      linePath: d,
      fillPath: fill,
      lastPoint: points[points.length - 1]
    };
  }, [values, width, height]);
  useEffect(() => {
    const timer = setTimeout(() => setDrawn(true), delay);
    return () => clearTimeout(timer);
  }, [delay]);
  return /*#__PURE__*/React.createElement("svg", {
    width: "100%",
    viewBox: `0 0 ${width} ${height}`,
    preserveAspectRatio: "none",
    style: {
      display: "block",
      overflow: "visible"
    }
  }, /*#__PURE__*/React.createElement("defs", null, /*#__PURE__*/React.createElement("linearGradient", {
    id: id + "-fill",
    x1: "0",
    y1: "0",
    x2: "0",
    y2: "1"
  }, /*#__PURE__*/React.createElement("stop", {
    offset: "0%",
    stopColor: color,
    stopOpacity: "0.45"
  }), /*#__PURE__*/React.createElement("stop", {
    offset: "100%",
    stopColor: color,
    stopOpacity: "0"
  })), /*#__PURE__*/React.createElement("linearGradient", {
    id: id + "-stroke",
    x1: "0",
    y1: "0",
    x2: "1",
    y2: "0"
  }, /*#__PURE__*/React.createElement("stop", {
    offset: "0%",
    stopColor: color,
    stopOpacity: "0.6"
  }), /*#__PURE__*/React.createElement("stop", {
    offset: "100%",
    stopColor: color,
    stopOpacity: "1"
  }))), fill && /*#__PURE__*/React.createElement("path", {
    d: fillPath,
    fill: `url(#${id}-fill)`,
    style: {
      opacity: drawn ? 1 : 0,
      transition: "opacity 600ms ease 300ms"
    }
  }), /*#__PURE__*/React.createElement("path", {
    ref: pathRef,
    d: linePath,
    fill: "none",
    stroke: gradient ? `url(#${id}-stroke)` : color,
    strokeWidth: thick ? 2.2 : 1.6,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    style: {
      strokeDasharray: 2000,
      strokeDashoffset: drawn ? 0 : 2000,
      transition: "stroke-dashoffset 1200ms cubic-bezier(0.25, 0.46, 0.45, 0.94)",
      filter: `drop-shadow(0 0 6px ${color}88)`
    }
  }), showDot && /*#__PURE__*/React.createElement("circle", {
    cx: lastPoint[0],
    cy: lastPoint[1],
    r: "2.6",
    fill: color,
    style: {
      opacity: drawn ? 1 : 0,
      transition: "opacity 400ms ease 1200ms",
      filter: `drop-shadow(0 0 6px ${color})`
    }
  }));
});

/* ── Animated number counter ──────────────────────────────── */
const Counter = ({
  to,
  duration = 1100,
  decimals = 0,
  prefix = "",
  suffix = "",
  className = ""
}) => {
  const [val, setVal] = useState(0);
  const ref = useRef(null);
  useEffect(() => {
    let start = null;
    let raf;
    const tick = ts => {
      if (!start) start = ts;
      const t = Math.min((ts - start) / duration, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      setVal(eased * to);
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [to, duration]);
  return /*#__PURE__*/React.createElement("span", {
    ref: ref,
    className: className
  }, prefix, decimals > 0 ? val.toFixed(decimals) : Math.round(val), suffix);
};

/* ── StanceDot ────────────────────────────────────────────── */
const StanceDot = ({
  stance,
  size = 8,
  style = {}
}) => {
  const colors = {
    supportive: "#34d399",
    critical: "#fb7185",
    neutral: "#a78bfa"
  };
  const c = colors[stance] || colors.neutral;
  return /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-block",
      width: size,
      height: size,
      borderRadius: "50%",
      background: c,
      boxShadow: `0 0 ${size}px ${c}`,
      flex: "none",
      ...style
    }
  });
};

/* ── LanguagePill ─────────────────────────────────────────── */
const LanguagePill = ({
  lang
}) => {
  const labels = {
    telugu: "TE",
    hindi: "HI",
    english: "EN",
    other: "OTH"
  };
  return /*#__PURE__*/React.createElement("span", {
    className: `lang-pill ${lang}`
  }, /*#__PURE__*/React.createElement("span", {
    className: "pill-dot"
  }), labels[lang] || "—");
};

/* ── LiveDot ──────────────────────────────────────────────── */
const LiveDot = ({
  tone = "live"
}) => /*#__PURE__*/React.createElement("span", {
  className: `live-dot ${tone}`
});

/* ── Reveal on scroll wrapper ─────────────────────────────── */
const Reveal = ({
  children,
  className = "",
  delay = 0
}) => {
  const ref = useRef(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const obs = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setTimeout(() => setSeen(true), delay);
        obs.disconnect();
      }
    }, {
      threshold: 0.05,
      rootMargin: "0px 0px -40px 0px"
    });
    if (ref.current) obs.observe(ref.current);
    return () => obs.disconnect();
  }, [delay]);
  return /*#__PURE__*/React.createElement("div", {
    ref: ref,
    className: `reveal ${seen ? "in" : ""} ${className}`
  }, children);
};

/* ── Section Header ───────────────────────────────────────── */
const SectionHead = ({
  icon,
  label,
  subtitle,
  accent = "#e9c46a"
}) => /*#__PURE__*/React.createElement("div", {
  className: "section-head"
}, /*#__PURE__*/React.createElement("div", {
  className: "eyebrow",
  style: {
    color: accent
  }
}, icon && /*#__PURE__*/React.createElement(Icon, {
  name: icon,
  size: 14,
  stroke: 1.8
}), /*#__PURE__*/React.createElement("span", null, label)), subtitle && /*#__PURE__*/React.createElement("div", {
  className: "subtitle"
}, subtitle));
window.RIG = window.RIG || {};
Object.assign(window.RIG, {
  Icon,
  Sparkline,
  Counter,
  StanceDot,
  LanguagePill,
  LiveDot,
  Reveal,
  SectionHead
});
})();
