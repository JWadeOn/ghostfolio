import { useState } from 'react';

const C = {
  bg: '#0B0F19',
  surface: '#111827',
  border: '#1E293B',
  borderLight: '#334155',
  text: '#E2E8F0',
  textMuted: '#94A3B8',
  textDim: '#475569',
  accent: '#00E5A0',
  accentDim: '#00E5A020',
  llm: '#A78BFA',
  llmDim: '#A78BFA18',
  code: '#38BDF8',
  codeDim: '#38BDF818',
  warn: '#FB923C',
  warnDim: '#FB923C18',
  ghost: '#6EE7B7',
  ghostDim: '#6EE7B718',
  red: '#F87171',
  redDim: '#F8717118',
  line: '#334155'
};

const fonts = {
  mono: "'JetBrains Mono', 'Fira Code', monospace",
  sans: "'DM Sans', 'Helvetica Neue', sans-serif",
  display: "'Instrument Sans', 'DM Sans', sans-serif"
};

// ── Shared Components ──
const Arrow = ({
  x1,
  y1,
  x2,
  y2,
  color = C.line,
  dashed = false,
  label = '',
  labelOffsetX = 0,
  labelOffsetY = -10
}) => {
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const headLen = 8;
  return (
    <g>
      <line
        x1={x1}
        y1={y1}
        x2={x2}
        y2={y2}
        stroke={color}
        strokeWidth={1.5}
        strokeDasharray={dashed ? '6 4' : 'none'}
        markerEnd="none"
      />
      <polygon
        points={`${x2},${y2} ${x2 - headLen * Math.cos(angle - 0.4)},${y2 - headLen * Math.sin(angle - 0.4)} ${x2 - headLen * Math.cos(angle + 0.4)},${y2 - headLen * Math.sin(angle + 0.4)}`}
        fill={color}
      />
      {label && (
        <text
          x={(x1 + x2) / 2 + labelOffsetX}
          y={(y1 + y2) / 2 + labelOffsetY}
          fill={C.textDim}
          fontSize={9}
          fontFamily={fonts.mono}
          textAnchor="middle"
        >
          {label}
        </text>
      )}
    </g>
  );
};

const Box = ({
  x,
  y,
  w,
  h,
  label,
  sublabel,
  color,
  bgColor,
  icon,
  radius = 8,
  fontSize = 11
}) => (
  <g>
    <rect
      x={x}
      y={y}
      width={w}
      height={h}
      rx={radius}
      fill={bgColor || C.surface}
      stroke={color || C.border}
      strokeWidth={1.5}
    />
    {icon && (
      <text
        x={x + 12}
        y={y + h / 2 + 1}
        fill={color || C.text}
        fontSize={13}
        fontFamily={fonts.sans}
        dominantBaseline="middle"
      >
        {icon}
      </text>
    )}
    <text
      x={icon ? x + 28 : x + w / 2}
      y={sublabel ? y + h / 2 - 5 : y + h / 2 + 1}
      fill={C.text}
      fontSize={fontSize}
      fontWeight="600"
      fontFamily={fonts.sans}
      textAnchor={icon ? 'start' : 'middle'}
      dominantBaseline="middle"
    >
      {label}
    </text>
    {sublabel && (
      <text
        x={icon ? x + 28 : x + w / 2}
        y={y + h / 2 + 10}
        fill={C.textDim}
        fontSize={8}
        fontFamily={fonts.mono}
        textAnchor={icon ? 'start' : 'middle'}
        dominantBaseline="middle"
      >
        {sublabel}
      </text>
    )}
  </g>
);

const Badge = ({ x, y, label, color }) => (
  <g>
    <rect
      x={x}
      y={y}
      width={label.length * 6.2 + 12}
      height={16}
      rx={3}
      fill={color + '18'}
      stroke={color + '40'}
      strokeWidth={0.5}
    />
    <text
      x={x + 6}
      y={y + 11}
      fill={color}
      fontSize={8}
      fontWeight="700"
      fontFamily={fonts.mono}
      letterSpacing="0.5"
    >
      {label}
    </text>
  </g>
);

// ── Diagram 1: Agentic Loop ──
const AgenticLoopDiagram = () => (
  <svg viewBox="0 0 780 620" style={{ width: '100%', height: 'auto' }}>
    {/* Background */}
    <rect width="780" height="620" fill={C.bg} rx={12} />

    {/* Title */}
    <text
      x="390"
      y="32"
      fill={C.text}
      fontSize={16}
      fontWeight="700"
      fontFamily={fonts.display}
      textAnchor="middle"
      letterSpacing="-0.02em"
    >
      The Agentic Loop
    </text>
    <text
      x="390"
      y="50"
      fill={C.textDim}
      fontSize={10}
      fontFamily={fonts.mono}
      textAnchor="middle"
    >
      6 nodes · 1 conditional loop · 2 LLM calls in the happy path
    </text>

    {/* Legend */}
    <Badge x={20} y={14} label="LLM CALL" color={C.llm} />
    <Badge x={100} y={14} label="CODE (NO LLM)" color={C.code} />
    <Badge x={210} y={14} label="CONDITIONAL" color={C.warn} />

    {/* ── Node 1: Input ── */}
    <Box
      x={310}
      y={75}
      w={160}
      h={36}
      label="Trader Query"
      sublabel="natural language"
      color={C.textDim}
      bgColor={C.surface}
    />
    <Arrow x1={390} y1={111} x2={390} y2={140} color={C.line} />

    {/* ── Node 2: Intent Classification ── */}
    <rect
      x={270}
      y={140}
      width={240}
      height={56}
      rx={8}
      fill={C.llmDim}
      stroke={C.llm}
      strokeWidth={1.5}
    />
    <text
      x={286}
      y={160}
      fill={C.llm}
      fontSize={12}
      fontWeight="700"
      fontFamily={fonts.sans}
    >
      ① Intent Classification
    </text>
    <text x={286} y={178} fill={C.textDim} fontSize={9} fontFamily={fonts.mono}>
      LLM call #1 — categorize query type
    </text>
    <Badge x={430} y={148} label="LLM" color={C.llm} />

    {/* Intent branches */}
    <Arrow x1={390} y1={196} x2={390} y2={228} color={C.line} />

    {/* Branch labels */}
    <text
      x={180}
      y={218}
      fill={C.textDim}
      fontSize={8}
      fontFamily={fonts.mono}
      textAnchor="end"
    >
      regime · scan · risk
    </text>
    <text
      x={600}
      y={218}
      fill={C.textDim}
      fontSize={8}
      fontFamily={fonts.mono}
      textAnchor="start"
    >
      chart · journal · lookup
    </text>
    <line
      x1={195}
      y1={215}
      x2={390}
      y2={215}
      stroke={C.border}
      strokeWidth={0.5}
      strokeDasharray="3 3"
    />
    <line
      x1={390}
      y1={215}
      x2={585}
      y2={215}
      stroke={C.border}
      strokeWidth={0.5}
      strokeDasharray="3 3"
    />

    {/* ── Node 3: Context Check ── */}
    <rect
      x={270}
      y={228}
      width={240}
      height={56}
      rx={8}
      fill={C.codeDim}
      stroke={C.code}
      strokeWidth={1.5}
    />
    <text
      x={286}
      y={248}
      fill={C.code}
      fontSize={12}
      fontWeight="700"
      fontFamily={fonts.sans}
    >
      ② Context Check
    </text>
    <text x={286} y={266} fill={C.textDim} fontSize={9} fontFamily={fonts.mono}>
      Is cached regime/portfolio fresh?
    </text>
    <Badge x={442} y={236} label="CODE" color={C.code} />

    {/* Decision diamond */}
    <Arrow x1={390} y1={284} x2={390} y2={310} color={C.line} />
    <polygon
      points="390,310 410,325 390,340 370,325"
      fill={C.warnDim}
      stroke={C.warn}
      strokeWidth={1.5}
    />
    <text
      x={390}
      y={328}
      fill={C.warn}
      fontSize={7}
      fontWeight="700"
      fontFamily={fonts.mono}
      textAnchor="middle"
      dominantBaseline="middle"
    >
      ?
    </text>

    {/* Fresh path - straight down */}
    <Arrow
      x1={390}
      y1={340}
      x2={390}
      y2={370}
      color={C.accent}
      label="fresh"
      labelOffsetX={20}
    />

    {/* Stale path - go right to tools */}
    <Arrow
      x1={410}
      y1={325}
      x2={550}
      y2={325}
      color={C.warn}
      label="stale/missing"
      labelOffsetY={-12}
    />

    {/* ── Node 4: Tool Calls ── */}
    <rect
      x={550}
      y={275}
      width={200}
      height={220}
      rx={8}
      fill={C.codeDim}
      stroke={C.code}
      strokeWidth={1.5}
    />
    <text
      x={566}
      y={296}
      fill={C.code}
      fontSize={12}
      fontWeight="700"
      fontFamily={fonts.sans}
    >
      ③ Tool Execution
    </text>
    <Badge x={700} y={281} label="CODE" color={C.code} />

    {/* Tool list */}
    {[
      { name: 'get_market_data', y: 314 },
      { name: 'get_portfolio_snapshot', y: 334 },
      { name: 'detect_regime', y: 354 },
      { name: 'scan_strategies', y: 374 },
      { name: 'check_risk', y: 394 },
      { name: 'get_trade_history', y: 414 },
      { name: 'lookup_symbol', y: 434 }
    ].map((t, i) => (
      <g key={i}>
        <rect x={566} y={t.y - 9} width={168} height={17} rx={3} fill={C.bg} />
        <text
          x={576}
          y={t.y + 2}
          fill={C.textMuted}
          fontSize={8.5}
          fontFamily={fonts.mono}
        >
          {t.name}
        </text>
      </g>
    ))}
    <text
      x={650}
      y={465}
      fill={C.textDim}
      fontSize={8}
      fontFamily={fonts.mono}
      textAnchor="middle"
    >
      All deterministic. No LLM.
    </text>

    {/* Tools feed back into flow */}
    <Arrow
      x1={550}
      y1={460}
      x2={390}
      y2={460}
      color={C.code}
      label="structured data"
      labelOffsetY={-10}
    />
    <Arrow x1={390} y1={370} x2={390} y2={400} color={C.line} />

    {/* ── Node 5: Synthesis ── */}
    <rect
      x={240}
      y={400}
      width={200}
      height={56}
      rx={8}
      fill={C.llmDim}
      stroke={C.llm}
      strokeWidth={1.5}
    />
    <text
      x={256}
      y={420}
      fill={C.llm}
      fontSize={12}
      fontWeight="700"
      fontFamily={fonts.sans}
    >
      ④ Synthesis
    </text>
    <text x={256} y={438} fill={C.textDim} fontSize={9} fontFamily={fonts.mono}>
      LLM call #2 — data → insight
    </text>
    <Badge x={380} y={408} label="LLM" color={C.llm} />

    <Arrow x1={340} y1={456} x2={340} y2={485} color={C.line} />

    {/* ── Node 6: Verification ── */}
    <rect
      x={210}
      y={485}
      width={260}
      height={56}
      rx={8}
      fill={C.codeDim}
      stroke={C.code}
      strokeWidth={1.5}
    />
    <text
      x={226}
      y={505}
      fill={C.code}
      fontSize={12}
      fontWeight="700"
      fontFamily={fonts.sans}
    >
      ⑤ Verification
    </text>
    <text x={226} y={523} fill={C.textDim} fontSize={9} fontFamily={fonts.mono}>
      fact-check · confidence · guardrails
    </text>
    <Badge x={400} y={493} label="CODE" color={C.code} />

    {/* Verification decision */}
    <polygon
      points="340,555 360,570 340,585 320,570"
      fill={C.warnDim}
      stroke={C.warn}
      strokeWidth={1.5}
    />
    <text
      x={340}
      y={573}
      fill={C.warn}
      fontSize={7}
      fontWeight="700"
      fontFamily={fonts.mono}
      textAnchor="middle"
      dominantBaseline="middle"
    >
      ?
    </text>
    <Arrow x1={340} y1={541} x2={340} y2={555} color={C.line} />

    {/* Pass → Output */}
    <Arrow
      x1={340}
      y1={585}
      x2={340}
      y2={603}
      color={C.accent}
      label="pass"
      labelOffsetX={22}
    />

    {/* Fail → Loop back */}
    <line
      x1={320}
      y1={570}
      x2={160}
      y2={570}
      stroke={C.red}
      strokeWidth={1.5}
    />
    <line
      x1={160}
      y1={570}
      x2={160}
      y2={425}
      stroke={C.red}
      strokeWidth={1.5}
    />
    <Arrow
      x1={160}
      y1={425}
      x2={238}
      y2={425}
      color={C.red}
      label="fail → correct"
      labelOffsetX={-8}
      labelOffsetY={-10}
    />
    <text
      x={120}
      y={500}
      fill={C.red}
      fontSize={8}
      fontFamily={fonts.mono}
      textAnchor="middle"
      transform="rotate(-90,120,500)"
    >
      LLM call #3
    </text>

    {/* ── Node 7: Output ── */}
    <rect x={240} y={600} width={200} height={14} rx={4} fill={C.accent} />
    <text
      x={340}
      y={611}
      fill={C.bg}
      fontSize={9}
      fontWeight="700"
      fontFamily={fonts.mono}
      textAnchor="middle"
    >
      ⑥ STRUCTURED RESPONSE → TRADER
    </text>
  </svg>
);

// ── Diagram 2: Ghostfolio Integration ──
const GhostfolioIntegrationDiagram = () => (
  <svg viewBox="0 0 780 680" style={{ width: '100%', height: 'auto' }}>
    <rect width="780" height="680" fill={C.bg} rx={12} />

    <text
      x="390"
      y="32"
      fill={C.text}
      fontSize={16}
      fontWeight="700"
      fontFamily={fonts.display}
      textAnchor="middle"
      letterSpacing="-0.02em"
    >
      System Architecture — Ghostfolio Integration
    </text>
    <text
      x="390"
      y="50"
      fill={C.textDim}
      fontSize={10}
      fontFamily={fonts.mono}
      textAnchor="middle"
    >
      Python agent service alongside Ghostfolio's NestJS backend
    </text>

    {/* ── TRADER / FRONTEND ── */}
    <rect
      x={260}
      y={65}
      width={260}
      height={44}
      rx={8}
      fill={C.surface}
      stroke={C.border}
      strokeWidth={1.5}
    />
    <text
      x={316}
      y={82}
      fill={C.text}
      fontSize={12}
      fontWeight="700"
      fontFamily={fonts.sans}
    >
      🧑‍💻 Trader
    </text>
    <text x={316} y={98} fill={C.textDim} fontSize={9} fontFamily={fonts.mono}>
      React/Next.js Frontend
    </text>

    <Arrow
      x1={390}
      y1={109}
      x2={390}
      y2={142}
      color={C.line}
      label="natural language query"
    />

    {/* ══════ AGENT SERVICE BOX ══════ */}
    <rect
      x={60}
      y={142}
      width={660}
      height={300}
      rx={10}
      fill={C.bg}
      stroke={C.accent}
      strokeWidth={1.5}
      strokeDasharray="none"
    />
    <rect x={60} y={142} width={660} height={28} rx={10} fill={C.accentDim} />
    <rect x={60} y={156} width={660} height={14} fill={C.accentDim} />
    <text
      x={80}
      y={161}
      fill={C.accent}
      fontSize={12}
      fontWeight="700"
      fontFamily={fonts.display}
    >
      PYTHON AGENT SERVICE (FastAPI + LangGraph)
    </text>
    <text x={625} y={161} fill={C.textDim} fontSize={8} fontFamily={fonts.mono}>
      port 8000
    </text>

    {/* LangGraph Orchestrator */}
    <rect
      x={85}
      y={182}
      width={200}
      height={40}
      rx={6}
      fill={C.llmDim}
      stroke={C.llm}
      strokeWidth={1}
    />
    <text
      x={105}
      y={199}
      fill={C.llm}
      fontSize={10}
      fontWeight="700"
      fontFamily={fonts.sans}
    >
      LangGraph Orchestrator
    </text>
    <text x={105} y={212} fill={C.textDim} fontSize={8} fontFamily={fonts.mono}>
      intent → tools → synthesis → verify
    </text>

    {/* LLM */}
    <rect
      x={310}
      y={182}
      width={150}
      height={40}
      rx={6}
      fill={C.llmDim}
      stroke={C.llm}
      strokeWidth={1}
    />
    <text
      x={325}
      y={199}
      fill={C.llm}
      fontSize={10}
      fontWeight="700"
      fontFamily={fonts.sans}
    >
      Claude (Anthropic)
    </text>
    <text x={325} y={212} fill={C.textDim} fontSize={8} fontFamily={fonts.mono}>
      intent + synthesis + charts
    </text>

    {/* Verification */}
    <rect
      x={485}
      y={182}
      width={220}
      height={40}
      rx={6}
      fill={C.codeDim}
      stroke={C.code}
      strokeWidth={1}
    />
    <text
      x={500}
      y={199}
      fill={C.code}
      fontSize={10}
      fontWeight="700"
      fontFamily={fonts.sans}
    >
      Verification Layer
    </text>
    <text x={500} y={212} fill={C.textDim} fontSize={8} fontFamily={fonts.mono}>
      fact-check · confidence · guardrails
    </text>

    {/* Arrow between orchestrator and LLM */}
    <line
      x1={285}
      y1={202}
      x2={310}
      y2={202}
      stroke={C.llm}
      strokeWidth={1}
      strokeDasharray="3 2"
    />
    <line
      x1={460}
      y1={202}
      x2={485}
      y2={202}
      stroke={C.code}
      strokeWidth={1}
      strokeDasharray="3 2"
    />

    {/* ── 7 TOOLS ── */}
    <text
      x={85}
      y={240}
      fill={C.textMuted}
      fontSize={9}
      fontWeight="600"
      fontFamily={fonts.sans}
      letterSpacing="0.08em"
    >
      TOOL REGISTRY (7 TOOLS — ALL DETERMINISTIC)
    </text>

    {/* Tool boxes - row 1 */}
    {[
      {
        x: 85,
        label: 'get_market_data',
        sub: 'yfinance + indicators',
        color: C.accent
      },
      {
        x: 248,
        label: 'get_portfolio_snapshot',
        sub: 'Ghostfolio API',
        color: C.ghost
      },
      {
        x: 411,
        label: 'detect_regime',
        sub: '5-dim classification',
        color: C.code
      },
      { x: 574, label: 'scan_strategies', sub: 'rules engine', color: C.warn }
    ].map((t, i) => (
      <g key={i}>
        <rect
          x={t.x}
          y={252}
          width={150}
          height={36}
          rx={5}
          fill={C.bg}
          stroke={t.color}
          strokeWidth={1}
        />
        <text
          x={t.x + 8}
          y={267}
          fill={C.text}
          fontSize={8.5}
          fontWeight="600"
          fontFamily={fonts.mono}
        >
          {t.label}
        </text>
        <text
          x={t.x + 8}
          y={280}
          fill={C.textDim}
          fontSize={7.5}
          fontFamily={fonts.mono}
        >
          {t.sub}
        </text>
      </g>
    ))}

    {/* Tool boxes - row 2 */}
    {[
      {
        x: 85,
        label: 'check_risk',
        sub: 'position/sector limits',
        color: C.red
      },
      {
        x: 248,
        label: 'get_trade_history',
        sub: 'orders + outcomes',
        color: C.ghost
      },
      { x: 411, label: 'lookup_symbol', sub: 'symbol search', color: C.ghost }
    ].map((t, i) => (
      <g key={i}>
        <rect
          x={t.x}
          y={296}
          width={150}
          height={36}
          rx={5}
          fill={C.bg}
          stroke={t.color}
          strokeWidth={1}
        />
        <text
          x={t.x + 8}
          y={311}
          fill={C.text}
          fontSize={8.5}
          fontWeight="600"
          fontFamily={fonts.mono}
        >
          {t.label}
        </text>
        <text
          x={t.x + 8}
          y={324}
          fill={C.textDim}
          fontSize={7.5}
          fontFamily={fonts.mono}
        >
          {t.sub}
        </text>
      </g>
    ))}

    {/* Color legend for tools */}
    <g transform="translate(574, 296)">
      <rect
        width={150}
        height={36}
        rx={5}
        fill={C.bg}
        stroke={C.border}
        strokeWidth={1}
      />
      <circle cx={14} cy={10} r={3} fill={C.ghost} />
      <text
        x={22}
        y={13}
        fill={C.textDim}
        fontSize={7.5}
        fontFamily={fonts.mono}
      >
        = calls Ghostfolio API
      </text>
      <circle cx={14} cy={25} r={3} fill={C.accent} />
      <text
        x={22}
        y={28}
        fill={C.textDim}
        fontSize={7.5}
        fontFamily={fonts.mono}
      >
        = external data (yfinance)
      </text>
    </g>

    {/* State Store */}
    <rect
      x={85}
      y={346}
      width={300}
      height={34}
      rx={6}
      fill={C.surface}
      stroke={C.borderLight}
      strokeWidth={1}
    />
    <text
      x={100}
      y={363}
      fill={C.textMuted}
      fontSize={9}
      fontWeight="600"
      fontFamily={fonts.sans}
    >
      📦 Agent State
    </text>
    <text x={188} y={363} fill={C.textDim} fontSize={8} fontFamily={fonts.mono}>
      regime_cache · portfolio · data_cache · history
    </text>

    {/* LangSmith */}
    <rect
      x={405}
      y={346}
      width={300}
      height={34}
      rx={6}
      fill={C.surface}
      stroke={C.borderLight}
      strokeWidth={1}
    />
    <text
      x={420}
      y={363}
      fill={C.textMuted}
      fontSize={9}
      fontWeight="600"
      fontFamily={fonts.sans}
    >
      📊 LangSmith
    </text>
    <text x={480} y={363} fill={C.textDim} fontSize={8} fontFamily={fonts.mono}>
      traces · evals · cost tracking
    </text>

    {/* ── Connection zone ── */}
    <text
      x={390}
      y={408}
      fill={C.textDim}
      fontSize={9}
      fontFamily={fonts.mono}
      textAnchor="middle"
      letterSpacing="0.15em"
    >
      REST API CALLS (JWT / API KEY AUTH)
    </text>
    <line
      x1={100}
      y1={414}
      x2={680}
      y2={414}
      stroke={C.border}
      strokeWidth={1}
      strokeDasharray="4 3"
    />

    {/* Arrows down to Ghostfolio */}
    <Arrow
      x1={200}
      y1={395}
      x2={200}
      y2={455}
      color={C.ghost}
      dashed
      label="/portfolio/*"
      labelOffsetX={42}
      labelOffsetY={4}
    />
    <Arrow
      x1={390}
      y1={395}
      x2={390}
      y2={455}
      color={C.ghost}
      dashed
      label="/order, /watchlist"
      labelOffsetX={52}
      labelOffsetY={4}
    />
    <Arrow
      x1={580}
      y1={395}
      x2={580}
      y2={455}
      color={C.ghost}
      dashed
      label="/symbol/*"
      labelOffsetX={38}
      labelOffsetY={4}
    />

    {/* ══════ GHOSTFOLIO BOX ══════ */}
    <rect
      x={60}
      y={455}
      width={660}
      height={160}
      rx={10}
      fill={C.bg}
      stroke={C.ghost}
      strokeWidth={1.5}
    />
    <rect x={60} y={455} width={660} height={28} rx={10} fill={C.ghostDim} />
    <rect x={60} y={469} width={660} height={14} fill={C.ghostDim} />
    <text
      x={80}
      y={474}
      fill={C.ghost}
      fontSize={12}
      fontWeight="700"
      fontFamily={fonts.display}
    >
      GHOSTFOLIO (NestJS + Angular) — EXISTING, UNMODIFIED
    </text>
    <text x={640} y={474} fill={C.textDim} fontSize={8} fontFamily={fonts.mono}>
      port 3333
    </text>

    {/* Ghostfolio services */}
    {[
      { x: 85, label: 'PortfolioService', sub: 'holdings, performance, ROAI' },
      {
        x: 280,
        label: 'DataProviderService',
        sub: 'Yahoo, CoinGecko, 9 providers'
      },
      { x: 500, label: 'OrderService', sub: 'activities, transactions' }
    ].map((s, i) => (
      <g key={i}>
        <rect
          x={s.x}
          y={492}
          width={185}
          height={34}
          rx={5}
          fill={C.surface}
          stroke={C.border}
          strokeWidth={1}
        />
        <text
          x={s.x + 10}
          y={507}
          fill={C.text}
          fontSize={9}
          fontWeight="600"
          fontFamily={fonts.sans}
        >
          {s.label}
        </text>
        <text
          x={s.x + 10}
          y={519}
          fill={C.textDim}
          fontSize={7.5}
          fontFamily={fonts.mono}
        >
          {s.sub}
        </text>
      </g>
    ))}

    {/* Ghostfolio data layer */}
    <text
      x={85}
      y={546}
      fill={C.textMuted}
      fontSize={9}
      fontWeight="600"
      fontFamily={fonts.sans}
      letterSpacing="0.06em"
    >
      PRISMA + POSTGRESQL
    </text>

    {/* Existing models */}
    {[
      { x: 85, label: 'User' },
      { x: 155, label: 'Account' },
      { x: 240, label: 'Order' },
      { x: 310, label: 'SymbolProfile' },
      { x: 425, label: 'MarketData' },
      { x: 530, label: 'Watchlist' }
    ].map((m, i) => (
      <g key={i}>
        <rect
          x={m.x}
          y={554}
          width={m.label.length * 7.5 + 14}
          height={20}
          rx={4}
          fill={C.surface}
          stroke={C.border}
          strokeWidth={0.75}
        />
        <text
          x={m.x + 7}
          y={567}
          fill={C.textMuted}
          fontSize={8}
          fontFamily={fonts.mono}
        >
          {m.label}
        </text>
      </g>
    ))}

    {/* New models */}
    <text
      x={85}
      y={594}
      fill={C.accent}
      fontSize={8}
      fontWeight="600"
      fontFamily={fonts.mono}
      letterSpacing="0.04em"
    >
      NEW MODELS (agent adds):
    </text>
    {[
      { x: 85, label: 'Signal' },
      { x: 155, label: 'Strategy' },
      { x: 240, label: 'RegimeClass.' },
      { x: 345, label: 'BacktestResult' },
      { x: 465, label: 'TradeJournal' }
    ].map((m, i) => (
      <g key={i}>
        <rect
          x={m.x}
          y={600}
          width={m.label.length * 7 + 14}
          height={20}
          rx={4}
          fill={C.accentDim}
          stroke={C.accent}
          strokeWidth={0.75}
        />
        <text
          x={m.x + 7}
          y={613}
          fill={C.accent}
          fontSize={8}
          fontFamily={fonts.mono}
        >
          {m.label}
        </text>
      </g>
    ))}

    {/* ── External data ── */}
    <rect
      x={60}
      y={635}
      width={230}
      height={38}
      rx={8}
      fill={C.surface}
      stroke={C.warn}
      strokeWidth={1}
    />
    <text
      x={80}
      y={651}
      fill={C.warn}
      fontSize={10}
      fontWeight="600"
      fontFamily={fonts.sans}
    >
      yfinance (OHLCV + Volume)
    </text>
    <text x={80} y={664} fill={C.textDim} fontSize={8} fontFamily={fonts.mono}>
      Full candle data for TA indicators
    </text>

    <rect
      x={310}
      y={635}
      width={200}
      height={38}
      rx={8}
      fill={C.surface}
      stroke={C.border}
      strokeWidth={1}
    />
    <text
      x={330}
      y={651}
      fill={C.textMuted}
      fontSize={10}
      fontWeight="600"
      fontFamily={fonts.sans}
    >
      Redis (Bull Queues)
    </text>
    <text x={330} y={664} fill={C.textDim} fontSize={8} fontFamily={fonts.mono}>
      Caching + background jobs
    </text>

    <rect
      x={530}
      y={635}
      width={190}
      height={38}
      rx={8}
      fill={C.surface}
      stroke={C.llm}
      strokeWidth={1}
    />
    <text
      x={550}
      y={651}
      fill={C.llm}
      fontSize={10}
      fontWeight="600"
      fontFamily={fonts.sans}
    >
      Anthropic API
    </text>
    <text x={550} y={664} fill={C.textDim} fontSize={8} fontFamily={fonts.mono}>
      Claude Sonnet 4.5
    </text>

    {/* Arrows from external to agent */}
    <Arrow x1={175} y1={635} x2={175} y2={442} color={C.warn} dashed />
    <Arrow x1={620} y1={635} x2={620} y2={442} color={C.llm} dashed />
  </svg>
);

// ── Main Export ──
export default function ArchitectureDiagrams() {
  const [view, setView] = useState('loop');
  return (
    <div
      style={{
        background: C.bg,
        minHeight: '100vh',
        padding: 24,
        fontFamily: fonts.sans
      }}
    >
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&family=Instrument+Sans:wght@400;500;600;700&display=swap');
      `}</style>

      <div style={{ maxWidth: 800, margin: '0 auto' }}>
        {/* Tab switcher */}
        <div
          style={{
            display: 'flex',
            gap: 4,
            marginBottom: 20,
            justifyContent: 'center'
          }}
        >
          {[
            { key: 'loop', label: 'Agentic Loop' },
            { key: 'integration', label: 'Ghostfolio Integration' }
          ].map((t) => (
            <button
              key={t.key}
              onClick={() => setView(t.key)}
              style={{
                padding: '8px 20px',
                border: 'none',
                borderRadius: 6,
                cursor: 'pointer',
                fontSize: 13,
                fontWeight: 600,
                fontFamily: fonts.sans,
                background: view === t.key ? C.accent : C.surface,
                color: view === t.key ? C.bg : C.textMuted,
                transition: 'all 0.15s ease'
              }}
            >
              {t.label}
            </button>
          ))}
        </div>

        {view === 'loop' && <AgenticLoopDiagram />}
        {view === 'integration' && <GhostfolioIntegrationDiagram />}
      </div>
    </div>
  );
}
