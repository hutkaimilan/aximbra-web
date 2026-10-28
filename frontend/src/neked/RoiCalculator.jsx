import { useState } from "react";
import { Slider } from "@/components/ui/slider";
import { fmtHuf, fmtNum } from "./lib";
import { SectionLabel } from "./QuoteCard";

const Control = ({ label, value, display, min, max, step, onChange, testId }) => (
  <div>
    <div className="mb-3 flex items-baseline justify-between gap-3">
      <span className="text-sm text-[var(--ax-muted)]">{label}</span>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(Math.max(0, Number(e.target.value) || 0))}
        className="w-28 rounded-md border border-[var(--ax-line)] bg-transparent px-2 py-1 text-right font-mono text-sm focus:border-[var(--ax-cyan)] focus:outline-none"
        aria-label={label}
        data-testid={`${testId}-input`}
      />
    </div>
    <Slider className="ax-slider" value={[Math.min(value, max)]} min={min} max={max} step={step} onValueChange={(v) => onChange(v[0])} data-testid={`${testId}-slider`} />
    <p className="mt-2 font-mono text-xs text-[var(--ax-muted)]">{display}</p>
  </div>
);

const Stat = ({ label, value, big, testId }) => (
  <div className="rounded-xl border border-[var(--ax-line)] p-4">
    <p className="text-xs text-[var(--ax-muted)]">{label}</p>
    <p className={`mt-1 font-mono font-bold break-words ${big ? "text-2xl text-[var(--ax-cyan)] sm:text-3xl" : "text-base"}`} data-testid={testId}>{value}</p>
  </div>
);

const Assumptions = ({ items, setItems, label }) => (
  <div className="mt-8">
    <p className="font-mono text-xs uppercase tracking-[0.2em] text-[var(--ax-purple)] mb-3">{label}</p>
    <ul className="flex flex-col gap-2" data-testid="roi-assumptions">
      {items.map((a, i) => (
        <li key={i} className="flex items-start gap-2">
          <span className="mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--ax-purple)]" />
          <textarea
            rows={2}
            value={a}
            onChange={(e) => setItems(items.map((x, j) => (j === i ? e.target.value : x)))}
            style={{ fieldSizing: "content" }}
            className="w-full resize-none rounded-md border border-transparent bg-transparent px-2 py-1 text-sm leading-relaxed text-slate-300 hover:border-[var(--ax-line)] focus:border-[var(--ax-cyan)] focus:outline-none"
            data-testid={`roi-assumption-${i}`}
          />
        </li>
      ))}
    </ul>
  </div>
);

export const RoiCalculator = ({ page }) => {
  const { ui, agent, lang } = page;
  const [hours, setHours] = useState(page.roi.hours_per_month);
  const [rate, setRate] = useState(page.roi.hourly_rate_huf);
  const [assumptions, setAssumptions] = useState(page.roi.assumptions);
  const monthly = hours * rate;
  const fee = agent.monthly_fee;
  const net = monthly - (fee || 0);
  // Az ajánlat szerint a próbahónap ingyenes, utána csak az ár felét kérjük.
  const payback = agent.price_min && net > 0 ? Math.max(1, Math.ceil((agent.price_min / 2) / net)) : null;
  const isHu = lang.toLowerCase().startsWith("hu");
  const price = isHu || !agent.price_max ? agent.price_text : `${fmtHuf(agent.price_min, lang)} – ${fmtHuf(agent.price_max, lang)}`;

  return (
    <section className="pb-16 sm:pb-24" data-testid="roi-calculator">
      <SectionLabel>{ui.roi_title}</SectionLabel>
      <div className="ax-card [display:grid] gap-8 p-5 sm:p-8 lg:grid-cols-2 lg:gap-12">
        <div>
          <div className="flex flex-col gap-8">
            <Control label={ui.roi_hours} value={hours} display={`${fmtNum(hours, lang)} h`} min={0} max={200} step={1} onChange={setHours} testId="roi-hours" />
            <Control label={ui.roi_rate} value={rate} display={fmtHuf(rate, lang)} min={2000} max={40000} step={500} onChange={setRate} testId="roi-rate" />
          </div>
          <Assumptions items={assumptions} setItems={setAssumptions} label={ui.roi_assumptions} />
        </div>
        <div className="[display:grid] content-start gap-3 sm:grid-cols-2">
          <Stat label={ui.roi_savings_month} value={fmtHuf(monthly, lang)} big testId="roi-monthly-savings" />
          <Stat label={ui.roi_savings_year} value={fmtHuf(monthly * 12, lang)} big testId="roi-yearly-savings" />
          <Stat label={ui.price_label} value={price} testId="roi-price" />
          <Stat label={ui.lead_label} value={agent.lead_text} testId="roi-lead-time" />
          <Stat label={ui.fee_label} value={fee ? `${fmtHuf(fee, lang)} ${ui.per_month}` : ui.on_quote} testId="roi-monthly-fee" />
          <Stat label={ui.payback_label} value={payback ? `~${payback} ${ui.months}` : "—"} testId="roi-payback" />
          <p className="text-xs text-[var(--ax-muted)] sm:col-span-2">{ui.approval_note}</p>
        </div>
      </div>
    </section>
  );
};
