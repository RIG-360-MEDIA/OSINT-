import { motion } from 'framer-motion';
import { Icons } from '../lib/ui';

const NAV = [
  { k: 'Home', ic: 'home' },
  { k: 'War Room', ic: 'warroom' },
  { k: 'Analytics', ic: 'analytics' },
  { k: 'Dossier', ic: 'dossier' },
  { k: 'Map', ic: 'map' },
  { k: 'Dispatch', ic: 'dispatch' },
];

export default function Sidebar({ i, setI, onCollapse }) {
  return (
    <nav className="rail">
      <div className="brand"><span className="r">RIG</span><span className="o">OSINT</span>
        {onCollapse && <button className="rail-collapse" title="Collapse menu" onClick={onCollapse}>«</button>}
      </div>
      {NAV.map((n, ix) => (
        <div key={n.k} className={'navitem' + (ix === i ? ' on' : '')} onClick={() => setI(ix)}>
          {ix === i && <motion.span layoutId="navpill" className="pill" transition={{ type: 'spring', stiffness: 380, damping: 32 }} />}
          {Icons[n.ic]}
          <span>{n.k}</span>
          <span className="ix">{String(ix + 1).padStart(2, '0')}</span>
        </div>
      ))}
      <div className="railfoot">NIGHT DESK<br />chrome is silence<br />— data is light</div>
    </nav>
  );
}
