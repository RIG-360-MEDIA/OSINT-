/**
 * DeviceShot — renders a real screenshot/mockup when `src` resolves, and a
 * tasteful dark placeholder (tag + title + skeleton bars) otherwise. Lets the
 * layout ship now and accept generated images later by dropping files into
 * public/ — no code change beyond the path.
 */
import { useState } from 'react';

/**
 * @param {{ src?: string, tag: string, title: string }} props
 */
export default function DeviceShot({ src, tag, title }) {
  const [failed, setFailed] = useState(false);
  if (src && !failed) {
    return <img src={src} alt={title} loading="lazy" onError={() => setFailed(true)} />;
  }
  return (
    <div className="ndl-shot-ph">
      <span className="tag">{tag}</span>
      <span className="ttl">{title}</span>
      <div className="bars"><i /><i /><i /></div>
    </div>
  );
}
