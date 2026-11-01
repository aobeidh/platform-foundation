import { NavLink } from 'react-router-dom';
import { CountBadge } from '@/ui/atoms/misc';
import { cn } from '@/lib/utils';

export function NavItem({ to, icon, label, count, onNavigate, end }: {
  to: string; icon: React.ReactNode; label: string; count?: number; onNavigate?: () => void; end?: boolean;
}) {
  return (
    <NavLink to={to} end={end} onClick={onNavigate}
      className={({ isActive }) => cn('flex items-center gap-2.5 rounded-[8px] px-3 py-2 text-[13.5px] font-medium transition [&_svg]:size-[18px] [&_svg]:shrink-0 [&_svg]:stroke-[1.75]',
        isActive ? 'bg-accent/10 text-accent' : 'text-muted hover:bg-panel2 hover:text-fg')}>
      {icon}
      <span className="truncate">{label}</span>
      {count !== undefined && <CountBadge count={count} className="ms-auto" />}
    </NavLink>
  );
}
