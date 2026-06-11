export default function Panel({ label, gold, hero, className = '', style, children }) {
  return (
    <div className={'panel' + (hero ? ' hero' : '') + (className ? ' ' + className : '')} style={style}>
      {label && <div className={'label' + (gold ? ' gold' : '')}>{label}</div>}
      {children}
    </div>
  );
}
