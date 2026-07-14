/* Post-login product chooser. Appears once the user is authenticated and is
   allowed to see the Company OSINT demo. Political Desk is always available;
   the Windlass company product is gated by a client-side demo allowlist. */
import { motion } from 'framer-motion';

export default function ProductPicker({ me, onPick }) {
  return (
    <div className="co-picker">
      <motion.div className="co-picker-in" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .5 }}>
        <h2>Choose a workspace</h2>
        <p>Signed in as {me?.email}. Pick the intelligence product you want to open.</p>
        <div className="co-picker-grid">
          <motion.button className="co-prod" onClick={() => onPick('political')} whileHover={{ y: -3 }}>
            <div className="pic" style={{ background: 'linear-gradient(140deg,#3a2f6e,#1c1740)' }}>🛰️</div>
            <div className="pt">Political Desk</div>
            <div className="pd">The live OSINT night-desk — regional political signals, war-room, coverage map and analyst RAG.</div>
          </motion.button>
          <motion.button className="co-prod" onClick={() => onPick('company')} whileHover={{ y: -3 }}>
            <div className="pic" style={{ background: 'linear-gradient(140deg,#0e8f8a,#0a6f6b)' }}>⚔️</div>
            <div className="pt">Windlass — Company OSINT</div>
            <div className="pd">Corporate intelligence for Windlass Steelcrafts: global sword tenders, expansion markets, competitors, social presence and trade signals.</div>
          </motion.button>
        </div>
      </motion.div>
    </div>
  );
}

/* Client-side gate: who may see the Windlass demo product. */
const DEMO_EMAILS = new Set([
  'tdsworks@gmail.com',
  'pranavsinghpuri09@gmail.com',
]);
export function canSeeCompany(me) {
  if (!me) return false;
  if (me.role === 'super_user') return true;
  return DEMO_EMAILS.has((me.email || '').toLowerCase());
}
