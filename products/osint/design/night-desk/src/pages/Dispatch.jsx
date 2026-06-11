import { Reveal } from '../lib/ui';
import ReportDispatch from '../components/ReportDispatch';

export default function Dispatch() {
  return (
    <div className="page stack">
      <Reveal>
        <div className="eyebrow">REPORTS &amp; DELIVERY</div>
        <h1 className="h-sec" style={{ marginTop: 6 }}>Dispatch</h1>
        <div className="sub">Compose, verify, and ship the daily intelligence brief — PDF or Gmail.</div>
      </Reveal>

      <Reveal><ReportDispatch /></Reveal>
    </div>
  );
}
