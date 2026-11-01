import { useEffect, useState } from 'react';
import { Search } from 'lucide-react';
import { Input } from '@/ui/atoms/input';
import { cn } from '@/lib/utils';

/** A debounced search field. */
export function SearchBox({ value, onChange, placeholder, className, delay = 150 }: {
  value: string; onChange: (v: string) => void; placeholder: string; className?: string; delay?: number;
}) {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  useEffect(() => {
    if (text === value) return;
    const id = setTimeout(() => onChange(text), delay);
    return () => clearTimeout(id);
  }, [text, value, onChange, delay]);
  return (
    <div className={cn('w-56', className)}>
      <Input type="search" icon={<Search />} value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} aria-label={placeholder} />
    </div>
  );
}
