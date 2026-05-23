import type { KeyboardEvent, MouseEvent } from 'react';
import {
  RESIZE_HANDLES,
  type ResizeDirection,
} from '@/lib/ticker-card-utils';

interface TickerResizeHandlesProps {
  symbol: string;
  onResizeStart: (event: MouseEvent, direction: ResizeDirection) => void;
  onResizeKeyDown: (event: KeyboardEvent<HTMLDivElement>) => void;
}

export function TickerResizeHandles({ symbol, onResizeStart, onResizeKeyDown }: TickerResizeHandlesProps) {
  return (
    <>
      {RESIZE_HANDLES.map((handle) => (
        <div
          key={handle.direction}
          className={handle.className}
          role="separator"
          aria-label={`${handle.label} ${symbol}`}
          onMouseDown={(e) => onResizeStart(e, handle.direction)}
        />
      ))}

      <div
        className="sp-resize-handle-keyboard"
        role="separator"
        tabIndex={0}
        aria-label={`Resize ${symbol} card. Use arrow keys to resize.`}
        onKeyDown={onResizeKeyDown}
        style={{ position: 'absolute', right: 4, bottom: 4, width: 1, height: 1, opacity: 0, pointerEvents: 'none' }}
      />
    </>
  );
}
