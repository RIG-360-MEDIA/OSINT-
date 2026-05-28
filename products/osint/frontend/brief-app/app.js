/* compiled from app.jsx — do not edit directly */
(function(){
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* global React, window */
// All page sections for RIG Intelligence Morning Brief

const {
  Icon,
  Sparkline,
  Counter,
  StanceDot,
  LanguagePill,
  LiveDot,
  Reveal,
  SectionHead
} = window.RIG;
const {
  SPARK,
  STORIES,
  ENTITIES,
  HORIZON,
  VOICES,
  CLIMBING,
  BLINDSPOT,
  RECOMMENDED
} = window.RIG_DATA;
const stanceColor = s => s === "supportive" ? "var(--stance-supportive)" : s === "critical" ? "var(--stance-critical)" : "var(--stance-neutral)";
const ringColor = r => ({
  violet: "#a78bfa",
  teal: "#5eead4",
  amber: "#fbbf24",
  rose: "#fb7185",
  emerald: "#34d399",
  blue: "#60a5fa",
  purple: "#c084fc",
  pink: "#f472b6"
})[r] || "#a78bfa";

/* ════════════════════════════════════════════════════════════
   TOP BAR
   ════════════════════════════════════════════════════════════ */
const TopBar = () => /*#__PURE__*/React.createElement("header", {
  className: "topbar"
}, /*#__PURE__*/React.createElement("div", {
  className: "container topbar-inner"
}, /*#__PURE__*/React.createElement("div", {
  className: "wordmark"
}, /*#__PURE__*/React.createElement("span", {
  className: "rig"
}, "RIG"), /*#__PURE__*/React.createElement("span", {
  className: "osint-stamp"
}, "OSINT")), /*#__PURE__*/React.createElement("label", {
  className: "ask-bar",
  tabIndex: 0
}, /*#__PURE__*/React.createElement(Icon, {
  name: "search",
  size: 14,
  color: "#64748b",
  stroke: 1.6
}), /*#__PURE__*/React.createElement("span", {
  className: "ph"
}, "Ask anything about today\u2026"), /*#__PURE__*/React.createElement("span", {
  className: "arr"
}, "\u2192")), /*#__PURE__*/React.createElement("div", {
  style: {
    display: "flex",
    alignItems: "center",
    gap: 10
  }
}, /*#__PURE__*/React.createElement("button", {
  className: "action-pill send"
}, /*#__PURE__*/React.createElement("span", null, "Send Report")), /*#__PURE__*/React.createElement("button", {
  className: "action-pill icon-only",
  title: "Export"
}, /*#__PURE__*/React.createElement(Icon, {
  name: "download",
  size: 13
})), /*#__PURE__*/React.createElement("span", {
  className: "avatar"
}, "M"))));

/* ════════════════════════════════════════════════════════════
   HERO PRELUDE
   ════════════════════════════════════════════════════════════ */
const HeroPrelude = () => /*#__PURE__*/React.createElement("section", {
  className: "container prelude"
}, /*#__PURE__*/React.createElement("h1", {
  className: "prelude-title"
}, "Morning Brief"), /*#__PURE__*/React.createElement("div", {
  className: "prelude-date"
}, "Tuesday, 13 May 2026"));

/* ════════════════════════════════════════════════════════════
   SECTION 1: MOOD / LAST 24 HOURS
   ════════════════════════════════════════════════════════════ */
const KpiTile = ({
  label,
  value,
  suffix = "",
  decimals = 0,
  prefix = "",
  tone,
  spark,
  langStack,
  delay = 0,
  arrow
}) => /*#__PURE__*/React.createElement("div", {
  className: `kpi-tile ${tone}`
}, /*#__PURE__*/React.createElement("div", {
  className: "lbl"
}, label), /*#__PURE__*/React.createElement("div", {
  className: "num"
}, /*#__PURE__*/React.createElement(Counter, {
  to: value,
  decimals: decimals,
  prefix: prefix,
  suffix: suffix,
  duration: 1100 + delay
}), arrow && /*#__PURE__*/React.createElement("span", {
  className: "arrow-down"
}, "\u2193")), spark && /*#__PURE__*/React.createElement("div", {
  style: {
    height: 32,
    marginTop: 4
  }
}, /*#__PURE__*/React.createElement(Sparkline, {
  values: SPARK[spark],
  height: 32,
  color: tone === "violet" ? "#e9c46a" : tone === "cyan" ? "#5eead4" : tone === "rose" ? "#fb7185" : "#cbd5e1",
  delay: 400 + delay
})), langStack && /*#__PURE__*/React.createElement("div", {
  className: "lang-stack tab-nums"
}, /*#__PURE__*/React.createElement("div", {
  className: "ln"
}, /*#__PURE__*/React.createElement("span", {
  className: "lbl"
}, "TE"), /*#__PURE__*/React.createElement("span", {
  className: "n"
}, "142")), /*#__PURE__*/React.createElement("div", {
  className: "ln"
}, /*#__PURE__*/React.createElement("span", {
  className: "lbl"
}, "HI"), /*#__PURE__*/React.createElement("span", {
  className: "n"
}, "38")), /*#__PURE__*/React.createElement("div", {
  className: "ln"
}, /*#__PURE__*/React.createElement("span", {
  className: "lbl"
}, "EN"), /*#__PURE__*/React.createElement("span", {
  className: "n"
}, "67"))));
const MoodSection = () => /*#__PURE__*/React.createElement(Reveal, null, /*#__PURE__*/React.createElement("section", {
  className: "container section",
  style: {
    paddingTop: 16
  }
}, /*#__PURE__*/React.createElement("div", {
  className: "glass elevated mood-card"
}, /*#__PURE__*/React.createElement("div", {
  className: "gradient-edge"
}), /*#__PURE__*/React.createElement("div", {
  className: "mood-head"
}, /*#__PURE__*/React.createElement("div", {
  style: {
    display: "inline-flex",
    alignItems: "center",
    gap: 12,
    color: "#e9c46a",
    fontFamily: "var(--font-mono)",
    fontSize: 11,
    letterSpacing: "0.22em",
    textTransform: "uppercase"
  }
}, /*#__PURE__*/React.createElement("span", {
  style: {
    display: "inline-block",
    width: 14,
    height: 1,
    background: "currentColor"
  }
}), /*#__PURE__*/React.createElement("span", null, "The Last 24 Hours")), /*#__PURE__*/React.createElement("div", {
  className: "t-mono"
}, "Overnight synthesis \xB7 Compiled 05:42 IST")), /*#__PURE__*/React.createElement("div", {
  className: "kpi-row"
}, /*#__PURE__*/React.createElement(KpiTile, {
  label: "Articles Parsed",
  value: 247,
  tone: "violet",
  spark: "articles",
  delay: 0
}), /*#__PURE__*/React.createElement(KpiTile, {
  label: "Outlets",
  value: 18,
  tone: "cyan",
  spark: "outlets",
  delay: 100
}), /*#__PURE__*/React.createElement(KpiTile, {
  label: "Languages",
  value: 3,
  tone: "emerald",
  langStack: true,
  delay: 200
}), /*#__PURE__*/React.createElement(KpiTile, {
  label: "Sentiment",
  value: -0.4,
  decimals: 1,
  tone: "rose",
  spark: "sentiment",
  delay: 300,
  arrow: true
})), /*#__PURE__*/React.createElement("div", {
  className: "mood-body"
}, /*#__PURE__*/React.createElement("div", {
  className: "synthesis"
}, /*#__PURE__*/React.createElement("p", null, "Overnight discourse pivoted from the ", /*#__PURE__*/React.createElement("span", {
  className: "entity-link"
}, "Musi Rejuvenation"), " announcement toward fiscal-credibility framing, driven primarily by a 02:14 IST tweet from", /*#__PURE__*/React.createElement("span", {
  className: "entity-link"
}, " KTR"), " citing the \u20B985,000 crore Kaleshwaram overrun figure. Telugu vernaculars \u2014 ", /*#__PURE__*/React.createElement("span", {
  className: "entity-link"
}, "Eenadu"), ", ", /*#__PURE__*/React.createElement("span", {
  className: "entity-link"
}, "V6 News"), ",", /*#__PURE__*/React.createElement("span", {
  className: "entity-link"
}, " Sakshi"), " \u2014 led overwhelmingly critical, with displacement testimony from the", /*#__PURE__*/React.createElement("span", {
  className: "entity-link"
}, " Kothagudem"), " corridor providing the strongest emotional anchor.", /*#__PURE__*/React.createElement("span", {
  className: "cite"
}, "1"), /*#__PURE__*/React.createElement("span", {
  className: "cite"
}, "2")), /*#__PURE__*/React.createElement("p", null, "English desks took a measurably more descriptive posture. ", /*#__PURE__*/React.createElement("span", {
  className: "entity-link"
}, "The Hindu"), ",", /*#__PURE__*/React.createElement("span", {
  className: "entity-link"
}, " Indian Express"), " and ", /*#__PURE__*/React.createElement("span", {
  className: "entity-link"
}, "Mint"), " foregrounded the funding-architecture question and the cabinet's \u20B91,500 crore Phase 1 clearance without taking up the land-acquisition grievance that dominates regional bulletins. The asymmetry is consistent with the seven-day rolling baseline (correlation 0.82). ", /*#__PURE__*/React.createElement("span", {
  className: "cite"
}, "3")), /*#__PURE__*/React.createElement("p", null, /*#__PURE__*/React.createElement("span", {
  className: "entity-link"
}, "CM Revanth Reddy"), "'s ", /*#__PURE__*/React.createElement("span", {
  className: "entity-link"
}, "Khammam"), " rally line \u2014 that BRS \"wasted \u20B940,000 crore\" \u2014 was repeated verbatim by three Hindi outlets but received only descriptive English coverage. The principal should expect this framing to harden into a recurring attack line, given the party's ", /*#__PURE__*/React.createElement("span", {
  className: "entity-link"
}, "Karimnagar"), " rally on Sunday is being pre-positioned along similar fiscal-mismanagement themes. ", /*#__PURE__*/React.createElement("span", {
  className: "cite"
}, "4")), /*#__PURE__*/React.createElement("p", null, "A small, favourable signal: the Adilabad farmer-loan-waiver second tranche was announced at Mancherial without English national coverage. The waiver is fiscally modest and politically clean; surfacing it to friendly desks today could rebalance the morning's net sentiment from \u22120.42 toward neutral. ", /*#__PURE__*/React.createElement("span", {
  className: "cite"
}, "5"))), /*#__PURE__*/React.createElement("aside", {
  className: "pull-quote"
}, /*#__PURE__*/React.createElement("div", {
  className: "hairline"
}), /*#__PURE__*/React.createElement("div", {
  className: "q"
}, "\"We will not build Telangana on press releases. We will build it on rivers, records, and receipts.\""), /*#__PURE__*/React.createElement("div", {
  className: "meta"
}, "\u2014 CM Revanth Reddy \xB7 Press Briefing \xB7 12 May 2026"))), /*#__PURE__*/React.createElement("div", {
  className: "mood-footer"
}, /*#__PURE__*/React.createElement("div", {
  className: "meta-group"
}, /*#__PURE__*/React.createElement("span", null, "Sources scanned \xB7 ", /*#__PURE__*/React.createElement("span", {
  className: "num tab-nums"
}, "247")), /*#__PURE__*/React.createElement("span", {
  className: "lang-inline"
}, /*#__PURE__*/React.createElement("span", {
  className: "lpair"
}, /*#__PURE__*/React.createElement("span", {
  className: "lbl"
}, "TE"), /*#__PURE__*/React.createElement("span", {
  className: "n tab-nums"
}, "142")), /*#__PURE__*/React.createElement("span", {
  className: "lpair"
}, /*#__PURE__*/React.createElement("span", {
  className: "lbl"
}, "HI"), /*#__PURE__*/React.createElement("span", {
  className: "n tab-nums"
}, "38")), /*#__PURE__*/React.createElement("span", {
  className: "lpair"
}, /*#__PURE__*/React.createElement("span", {
  className: "lbl"
}, "EN"), /*#__PURE__*/React.createElement("span", {
  className: "n tab-nums"
}, "67"))), /*#__PURE__*/React.createElement("span", null, "Process time \xB7 ", /*#__PURE__*/React.createElement("span", {
  className: "num tab-nums"
}, "4m 22s")), /*#__PURE__*/React.createElement("span", null, "Editorial desk \xB7 Hyderabad bureau")), /*#__PURE__*/React.createElement("button", {
  className: "icon-btn",
  title: "Refresh"
}, /*#__PURE__*/React.createElement(Icon, {
  name: "refresh",
  size: 13
}))))));

/* ════════════════════════════════════════════════════════════
   SECTION 2: DEFINING STORIES
   ════════════════════════════════════════════════════════════ */
const LensCard = ({
  outlet,
  lang,
  stance,
  quote
}) => /*#__PURE__*/React.createElement("div", {
  className: "lens-card"
}, /*#__PURE__*/React.createElement("div", {
  className: "lens-top"
}, /*#__PURE__*/React.createElement(StanceDot, {
  stance: stance,
  size: 6
}), /*#__PURE__*/React.createElement("span", {
  className: "outlet"
}, outlet)), /*#__PURE__*/React.createElement(LanguagePill, {
  lang: lang
}), /*#__PURE__*/React.createElement("div", {
  className: "quote"
}, "\"", quote, "\""));
const StoryRow = ({
  story,
  idx
}) => /*#__PURE__*/React.createElement(Reveal, {
  delay: idx * 80
}, /*#__PURE__*/React.createElement("article", {
  className: "glass hoverable story",
  style: {
    "--stance": stanceColor(story.stance)
  }
}, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
  className: "rank"
}, story.rank, " / 05"), /*#__PURE__*/React.createElement("h2", {
  className: "headline"
}, story.headline), /*#__PURE__*/React.createElement("p", {
  className: "summary"
}, story.summary), /*#__PURE__*/React.createElement("div", {
  className: "meta-strip"
}, /*#__PURE__*/React.createElement("div", {
  style: {
    height: 28,
    maxWidth: 220
  }
}, /*#__PURE__*/React.createElement(Sparkline, {
  values: SPARK[story.spark],
  height: 28,
  color: story.stance === "critical" ? "#fb7185" : story.stance === "supportive" ? "#34d399" : "#a78bfa",
  showDot: true
})), /*#__PURE__*/React.createElement("div", {
  className: "metrics-line"
}, /*#__PURE__*/React.createElement("span", null, story.metrics.articles, " Articles"), /*#__PURE__*/React.createElement("span", null, "\xB7"), /*#__PURE__*/React.createElement("span", null, story.metrics.outlets, " Outlets"), /*#__PURE__*/React.createElement("span", null, "\xB7"), /*#__PURE__*/React.createElement("span", {
  className: "climbing"
}, "\u2191 ", story.metrics.vs, " vs baseline")), /*#__PURE__*/React.createElement("div", {
  className: "cov-bar",
  title: `crit ${story.coverage.crit} · neu ${story.coverage.neu} · sup ${story.coverage.sup}`
}, /*#__PURE__*/React.createElement("span", {
  className: "crit",
  style: {
    width: story.coverage.crit + "%"
  }
}), /*#__PURE__*/React.createElement("span", {
  className: "neu",
  style: {
    width: story.coverage.neu + "%"
  }
}), /*#__PURE__*/React.createElement("span", {
  className: "sup",
  style: {
    width: story.coverage.sup + "%"
  }
})), /*#__PURE__*/React.createElement("span", {
  className: "drill"
}, "Drill into evidence ", /*#__PURE__*/React.createElement(Icon, {
  name: "arrowRight",
  size: 12
})))), /*#__PURE__*/React.createElement("div", {
  className: "source-lens"
}, /*#__PURE__*/React.createElement("div", {
  className: "lens-head"
}, /*#__PURE__*/React.createElement("span", {
  className: "ttl"
}, "Source Lens \xB7 5 Perspectives")), /*#__PURE__*/React.createElement("div", {
  className: "lens-row"
}, story.lens.map((l, i) => /*#__PURE__*/React.createElement(LensCard, _extends({
  key: i
}, l)))), /*#__PURE__*/React.createElement("div", {
  className: "narrative-gap"
}, /*#__PURE__*/React.createElement("div", {
  className: "nbar"
}, /*#__PURE__*/React.createElement("span", {
  className: "crit",
  style: {
    width: story.coverage.crit + "%"
  }
}), /*#__PURE__*/React.createElement("span", {
  className: "neu",
  style: {
    width: story.coverage.neu + "%"
  }
}), /*#__PURE__*/React.createElement("span", {
  className: "sup",
  style: {
    width: story.coverage.sup + "%"
  }
})), /*#__PURE__*/React.createElement("div", {
  className: "caption"
}, "\"", story.caption, "\"")))));
const DefiningStories = () => /*#__PURE__*/React.createElement("section", {
  className: "container section"
}, /*#__PURE__*/React.createElement(Reveal, null, /*#__PURE__*/React.createElement(SectionHead, {
  label: "Today's Defining Stories",
  subtitle: "Five events shaping the discourse, framed by the outlets that matter."
})), /*#__PURE__*/React.createElement("div", null, STORIES.map((s, i) => /*#__PURE__*/React.createElement(React.Fragment, {
  key: s.rank
}, /*#__PURE__*/React.createElement(StoryRow, {
  story: s,
  idx: i
}), i < STORIES.length - 1 && /*#__PURE__*/React.createElement("div", {
  className: "story-divider"
})))));

/* ════════════════════════════════════════════════════════════
   SECTION 3: WATCHED ENTITIES
   ════════════════════════════════════════════════════════════ */
const EntityCard = ({
  entity,
  idx
}) => {
  const ring = ringColor(entity.ring);
  const sentPct = (entity.sentiment + 1) / 2 * 100;
  return /*#__PURE__*/React.createElement(Reveal, {
    delay: idx * 60
  }, /*#__PURE__*/React.createElement("article", {
    className: "glass hoverable entity-card",
    style: {
      "--ring-color": ring
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "halo",
    style: {
      background: ring
    }
  }), /*#__PURE__*/React.createElement("div", {
    className: "entity-top"
  }, /*#__PURE__*/React.createElement("div", {
    className: `portrait ${entity.icon ? "icon" : ""}`
  }, /*#__PURE__*/React.createElement("div", {
    className: "face"
  }, entity.icon ? /*#__PURE__*/React.createElement(Icon, {
    name: entity.icon,
    size: 28,
    stroke: 1.5
  }) : entity.init)), /*#__PURE__*/React.createElement("div", {
    className: "entity-info"
  }, /*#__PURE__*/React.createElement("div", {
    className: "name"
  }, entity.name), /*#__PURE__*/React.createElement("div", {
    className: "role"
  }, entity.role)), entity.live && /*#__PURE__*/React.createElement(LiveDot, null)), /*#__PURE__*/React.createElement("div", {
    className: "entity-metrics"
  }, /*#__PURE__*/React.createElement("div", {
    className: "metric-row"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mentions"
  }, entity.mentions), /*#__PURE__*/React.createElement("span", null, "Mentions \xB7 24H"), /*#__PURE__*/React.createElement("span", {
    className: entity.change.startsWith("−") ? "down" : "up"
  }, entity.change)), /*#__PURE__*/React.createElement("div", {
    style: {
      height: 40,
      position: "relative"
    }
  }, /*#__PURE__*/React.createElement(Sparkline, {
    values: SPARK[entity.spark],
    height: 40,
    color: ring,
    thick: true
  })), /*#__PURE__*/React.createElement("div", {
    className: "sentiment-gauge"
  }, /*#__PURE__*/React.createElement("span", {
    className: "marker",
    style: {
      left: sentPct + "%"
    }
  })), /*#__PURE__*/React.createElement("div", {
    className: "sentiment-axis"
  }, /*#__PURE__*/React.createElement("span", null, "\u22121.0 critical"), /*#__PURE__*/React.createElement("span", null, "neutral"), /*#__PURE__*/React.createElement("span", null, "supportive +1.0"))), /*#__PURE__*/React.createElement("div", {
    className: "latest-block",
    style: {
      "--stance-color": stanceColor(entity.latest.stance)
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "lbl"
  }, /*#__PURE__*/React.createElement(StanceDot, {
    stance: entity.latest.stance,
    size: 6,
    style: {
      marginRight: 6,
      verticalAlign: "middle"
    }
  }), "Latest Quote"), /*#__PURE__*/React.createElement("div", {
    className: "quote"
  }, "\"", entity.latest.quote, "\""), /*#__PURE__*/React.createElement("div", {
    className: "ctx"
  }, entity.latest.ctx)), entity.tweet && /*#__PURE__*/React.createElement("div", {
    className: "tweet-block"
  }, /*#__PURE__*/React.createElement("div", {
    className: "top"
  }, /*#__PURE__*/React.createElement("span", {
    className: "handle"
  }, entity.tweet.handle), /*#__PURE__*/React.createElement("span", {
    className: "tw-time"
  }, entity.tweet.time)), /*#__PURE__*/React.createElement("div", {
    className: "body",
    dangerouslySetInnerHTML: {
      __html: entity.tweet.body
    }
  }), entity.tweet.hasImage && /*#__PURE__*/React.createElement("span", {
    className: "img-tag"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "image",
    size: 11
  }), /*#__PURE__*/React.createElement("span", null, "Image attached")))));
};
const WatchedEntities = () => /*#__PURE__*/React.createElement("section", {
  className: "container section"
}, /*#__PURE__*/React.createElement(Reveal, null, /*#__PURE__*/React.createElement(SectionHead, {
  label: "Watched \xB7 8 Entities \xB7 3 Hottest",
  subtitle: "Your tracked political actors and issues, with the last 24 hours of motion."
})), /*#__PURE__*/React.createElement("div", {
  className: "entity-grid"
}, ENTITIES.map((e, i) => /*#__PURE__*/React.createElement(EntityCard, {
  key: e.name,
  entity: e,
  idx: i
}))));

/* ════════════════════════════════════════════════════════════
   SECTION 4: HORIZON 7 DAYS
   ════════════════════════════════════════════════════════════ */
const eventColor = t => ({
  cabinet: "#5eead4",
  // muted teal
  press: "#fb7185",
  // muted rose
  rally: "#e9c46a",
  // saffron
  court: "#fb7185",
  // muted rose
  election: "#c084fc" // purple
})[t] || "#94a3b8";
const eventTypeLabel = t => ({
  cabinet: "Cabinet",
  press: "Press",
  rally: "Rally",
  court: "Court",
  election: "Election"
})[t] || "Event";
const DayCol = ({
  day,
  idx
}) => /*#__PURE__*/React.createElement("div", {
  className: `glass r-md day-col ${day.today ? "today" : ""}`
}, /*#__PURE__*/React.createElement("div", {
  className: "day"
}, day.day), /*#__PURE__*/React.createElement("div", {
  className: "date"
}, day.date), day.events && day.events.length > 0 ? day.events.map((ev, i) => /*#__PURE__*/React.createElement("div", {
  className: "event-chip",
  key: i,
  style: {
    "--evt": eventColor(ev.type)
  }
}, /*#__PURE__*/React.createElement("span", {
  className: "ttype"
}, eventTypeLabel(ev.type)), /*#__PURE__*/React.createElement("span", {
  className: "titl"
}, ev.title), /*#__PURE__*/React.createElement("span", {
  className: "src"
}, ev.src))) : /*#__PURE__*/React.createElement("div", {
  className: "empty"
}, "no items"));
const Horizon7Days = () => /*#__PURE__*/React.createElement("section", {
  className: "container section"
}, /*#__PURE__*/React.createElement(Reveal, null, /*#__PURE__*/React.createElement(SectionHead, {
  label: "On the Horizon \xB7 Next 7 Days",
  subtitle: "Scheduled and anticipated events ranked by political weight."
})), /*#__PURE__*/React.createElement(Reveal, null, /*#__PURE__*/React.createElement("div", {
  className: "horizon-grid"
}, HORIZON.map((d, i) => /*#__PURE__*/React.createElement(DayCol, {
  key: d.day,
  day: d,
  idx: i
}))), /*#__PURE__*/React.createElement("p", {
  className: "weather-narr"
}, "The week's barometer leans ", /*#__PURE__*/React.createElement("span", {
  className: "em"
}, "stormy"), ". Friday's cabinet meeting and the Monday Dharani High Court hearing are the two pressure points; the Sunday Karimnagar rally is the principal's clearest counter-narrative opportunity. Pre-position irrigation talking points before Wednesday's KTR presser, and treat Thursday's court-hearing prep as the higher-leverage briefing of the week.")));

/* ════════════════════════════════════════════════════════════
   SECTION 5: VOICES OVERNIGHT
   ════════════════════════════════════════════════════════════ */
const QuoteCard = ({
  q,
  idx
}) => /*#__PURE__*/React.createElement(Reveal, {
  delay: idx * 70
}, /*#__PURE__*/React.createElement("figure", {
  className: `glass hoverable quote-card ${q.size || ""}`,
  style: {
    "--stance": stanceColor(q.stance),
    "--ring-color": ringColor(q.ring)
  }
}, /*#__PURE__*/React.createElement("span", {
  className: "top-grad"
}), /*#__PURE__*/React.createElement(StanceDot, {
  stance: q.stance,
  size: 8,
  style: {
    position: "absolute",
    top: 16,
    left: 16
  }
}), /*#__PURE__*/React.createElement("blockquote", {
  className: "qbody"
}, "\"", q.quote, "\""), /*#__PURE__*/React.createElement("figcaption", {
  className: "chip-strip"
}, /*#__PURE__*/React.createElement("span", {
  className: "mini-portrait"
}, /*#__PURE__*/React.createElement("span", {
  className: "face"
}, q.init)), /*#__PURE__*/React.createElement("span", {
  className: "spk-name"
}, q.speaker), /*#__PURE__*/React.createElement("span", {
  className: "bullet"
}), /*#__PURE__*/React.createElement("span", {
  className: "venue"
}, q.venue), /*#__PURE__*/React.createElement("span", {
  className: "bullet"
}), /*#__PURE__*/React.createElement("span", {
  className: `ctx-pill ${q.ctx}`
}, q.ctx.replace("_", " ")))));
const VoicesOvernight = () => /*#__PURE__*/React.createElement("section", {
  className: "container section"
}, /*#__PURE__*/React.createElement(Reveal, null, /*#__PURE__*/React.createElement(SectionHead, {
  label: "Voices Overnight",
  subtitle: "Five quotes that defined the past 24 hours."
})), /*#__PURE__*/React.createElement("div", {
  className: "voices-grid"
}, VOICES.map((q, i) => /*#__PURE__*/React.createElement(QuoteCard, {
  key: i,
  q: q,
  idx: i
}))));

/* ════════════════════════════════════════════════════════════
   SECTION 6: CLIMBING WATCH
   ════════════════════════════════════════════════════════════ */
const ClimbingCard = ({
  c,
  idx
}) => /*#__PURE__*/React.createElement(Reveal, {
  delay: idx * 80
}, /*#__PURE__*/React.createElement("article", {
  className: "glass hoverable climbing-card"
}, /*#__PURE__*/React.createElement("div", {
  className: "spark-wrap"
}, /*#__PURE__*/React.createElement("span", {
  className: "spark-badge"
}, /*#__PURE__*/React.createElement("span", {
  style: {
    width: 5,
    height: 5,
    borderRadius: "50%",
    background: "currentColor"
  }
}), "\u2191 Climbing"), /*#__PURE__*/React.createElement("div", {
  style: {
    position: "absolute",
    inset: "40px 0 0",
    padding: "0 22px"
  }
}, /*#__PURE__*/React.createElement(Sparkline, {
  values: SPARK[c.spark],
  height: 130,
  color: "#fbbf24",
  thick: true,
  fill: true
}))), /*#__PURE__*/React.createElement("div", {
  className: "body"
}, /*#__PURE__*/React.createElement("h3", null, c.headline), /*#__PURE__*/React.createElement("div", {
  className: "mline"
}, "Mentions ", c.mentions, " \xB7 ", /*#__PURE__*/React.createElement("span", {
  className: "up"
}, "\u2191 ", c.vs), " \xB7 ", c.window), /*#__PURE__*/React.createElement("span", {
  className: `rec-pill ${c.recType}`
}, c.recType === "respond" && /*#__PURE__*/React.createElement(LiveDot, {
  tone: "amber"
}), c.rec))));
const ClimbingWatch = () => /*#__PURE__*/React.createElement("section", {
  className: "container section"
}, /*#__PURE__*/React.createElement(Reveal, null, /*#__PURE__*/React.createElement(SectionHead, {
  label: "Climbing \xB7 Stories Gaining Altitude",
  subtitle: "Velocity-detected stories likely to dominate evening bulletins.",
  accent: "var(--signal-climbing)"
})), /*#__PURE__*/React.createElement("div", {
  className: "climbing-grid"
}, CLIMBING.map((c, i) => /*#__PURE__*/React.createElement(ClimbingCard, {
  key: i,
  c: c,
  idx: i
}))));

/* ════════════════════════════════════════════════════════════
   SECTION 7: BLINDSPOT
   ════════════════════════════════════════════════════════════ */
const BlindRow = ({
  row,
  side
}) => /*#__PURE__*/React.createElement("div", {
  className: "blind-row"
}, /*#__PURE__*/React.createElement("span", {
  className: `dot ${side}`
}), /*#__PURE__*/React.createElement("div", {
  className: "text"
}, /*#__PURE__*/React.createElement("div", {
  className: "ttl"
}, row.title), /*#__PURE__*/React.createElement("div", {
  className: "stat"
}, side === "telugu" ? `Telugu outlets: ${row.t} · English: ${row.e}` : `English outlets: ${row.e} · Telugu: ${row.t}`)));
const BlindspotComparison = () => /*#__PURE__*/React.createElement("section", {
  className: "container section"
}, /*#__PURE__*/React.createElement(Reveal, null, /*#__PURE__*/React.createElement(SectionHead, {
  label: "Blindspot \xB7 Asymmetric Coverage",
  subtitle: "Stories one side of the press led with that the other ignored."
})), /*#__PURE__*/React.createElement(Reveal, null, /*#__PURE__*/React.createElement("div", {
  className: "blindspot-grid"
}, /*#__PURE__*/React.createElement("div", {
  className: "glass blind-card telugu"
}, /*#__PURE__*/React.createElement("div", {
  className: "gradient-wash"
}), /*#__PURE__*/React.createElement("div", {
  className: "head"
}, "Telugu Led \xB7 English Ignored"), /*#__PURE__*/React.createElement("div", {
  className: "sub"
}, "Stories that ruled the vernacular morning but never reached the national wires."), BLINDSPOT.telugu_led.map((r, i) => /*#__PURE__*/React.createElement(BlindRow, {
  key: i,
  row: r,
  side: "telugu"
}))), /*#__PURE__*/React.createElement("div", {
  className: "glass blind-card english"
}, /*#__PURE__*/React.createElement("div", {
  className: "gradient-wash"
}), /*#__PURE__*/React.createElement("div", {
  className: "head"
}, "English Led \xB7 Telugu Ignored"), /*#__PURE__*/React.createElement("div", {
  className: "sub"
}, "Analyses and angles confined to English national press; vernaculars passed."), BLINDSPOT.english_led.map((r, i) => /*#__PURE__*/React.createElement(BlindRow, {
  key: i,
  row: r,
  side: "english"
}))))));

/* ════════════════════════════════════════════════════════════
   SECTION 8: RECOMMENDED
   ════════════════════════════════════════════════════════════ */
const ArticleCard = ({
  a,
  idx
}) => /*#__PURE__*/React.createElement(Reveal, {
  delay: idx * 80
}, /*#__PURE__*/React.createElement("article", {
  className: "glass hoverable rec-card"
}, /*#__PURE__*/React.createElement("div", {
  className: `thumb ${a.outlet}`
}, /*#__PURE__*/React.createElement("span", {
  className: "outlet-stamp"
}, a.name)), /*#__PURE__*/React.createElement("div", {
  className: "body"
}, /*#__PURE__*/React.createElement("div", {
  className: "byline"
}, a.byline), /*#__PURE__*/React.createElement("h3", null, a.headline), /*#__PURE__*/React.createElement("p", {
  className: "summary"
}, "\"", a.summary, "\""), /*#__PURE__*/React.createElement("div", {
  className: "foot"
}, /*#__PURE__*/React.createElement("span", {
  className: "meta-foot"
}, a.meta), /*#__PURE__*/React.createElement("button", {
  className: "fwd-btn",
  title: "Forward to CM"
}, /*#__PURE__*/React.createElement(Icon, {
  name: "paperPlane",
  size: 13,
  stroke: 1.8
}))))));
const RecommendedReads = () => /*#__PURE__*/React.createElement("section", {
  className: "container section"
}, /*#__PURE__*/React.createElement(Reveal, null, /*#__PURE__*/React.createElement(SectionHead, {
  label: "Recommended for the CM",
  subtitle: "Three deep reads the CM should personally see.",
  accent: "var(--signal-climbing)"
})), /*#__PURE__*/React.createElement("div", {
  className: "rec-grid"
}, RECOMMENDED.map((a, i) => /*#__PURE__*/React.createElement(ArticleCard, {
  key: i,
  a: a,
  idx: i
}))));

/* ════════════════════════════════════════════════════════════
   FOOTER
   ════════════════════════════════════════════════════════════ */
const FooterStrip = () => /*#__PURE__*/React.createElement("footer", {
  className: "container footer-strip"
}, /*#__PURE__*/React.createElement("div", {
  className: "line"
}, "Compiled at 5:42 AM IST \xB7 247 articles \xB7 18 outlets \xB7 3 languages \xB7 Next refresh in 14 minutes."), /*#__PURE__*/React.createElement("div", {
  className: "sys"
}, /*#__PURE__*/React.createElement(LiveDot, null), "RIG Intelligence \xB7 v2.0.4 \xB7 session 8f2a4c \xB7 uptime 99.97%"));

/* ════════════════════════════════════════════════════════════
   APP
   ════════════════════════════════════════════════════════════ */
const App = () => /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
  className: "blob-layer"
}, /*#__PURE__*/React.createElement("div", {
  className: "blob violet"
}), /*#__PURE__*/React.createElement("div", {
  className: "blob cyan"
}), /*#__PURE__*/React.createElement("div", {
  className: "blob amber"
}), /*#__PURE__*/React.createElement("div", {
  className: "blob rose"
})), /*#__PURE__*/React.createElement("div", {
  className: "grain"
}), /*#__PURE__*/React.createElement("div", {
  className: "shell"
}, /*#__PURE__*/React.createElement(TopBar, null), /*#__PURE__*/React.createElement(HeroPrelude, null), /*#__PURE__*/React.createElement(MoodSection, null), /*#__PURE__*/React.createElement(DefiningStories, null), /*#__PURE__*/React.createElement(WatchedEntities, null), /*#__PURE__*/React.createElement(Horizon7Days, null), /*#__PURE__*/React.createElement(VoicesOvernight, null), /*#__PURE__*/React.createElement(ClimbingWatch, null), /*#__PURE__*/React.createElement(BlindspotComparison, null), /*#__PURE__*/React.createElement(RecommendedReads, null), /*#__PURE__*/React.createElement(FooterStrip, null)));
const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(/*#__PURE__*/React.createElement(App, null));
})();
