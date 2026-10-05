import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ExpandToggle } from './ExpandToggle';

describe('ExpandToggle', () => {
  it('shows the more label with the hidden count when closed', () => {
    render(<ExpandToggle open={false} onClick={() => {}} hiddenCount={4} />);
    expect(screen.getByRole('button', { name: /View more \(4\)/ })).toHaveAttribute('aria-expanded', 'false');
  });

  it('shows the less label when open', () => {
    render(<ExpandToggle open onClick={() => {}} />);
    expect(screen.getByRole('button', { name: /View less/ })).toHaveAttribute('aria-expanded', 'true');
  });

  it('calls onClick', async () => {
    const onClick = vi.fn();
    render(<ExpandToggle open={false} onClick={onClick} moreLabel="Show details" />);
    await userEvent.setup().click(screen.getByRole('button', { name: /Show details/ }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
