import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { ARRAY_LIMIT, JsonTree } from './JsonTree';

const DOC = { title: 'x', session: { id: 'S1', count: 3, ok: true, none: null }, list: ['alpha', 'beta', 'gamma'], empty: {} };

describe('JsonTree', () => {
  it('shows the top level and opens only the branches asked for', () => {
    render(<JsonTree data={DOC} openKeys={['session']} />);
    const tree = within(screen.getByRole('group', { name: 'Structured document' }));
    expect(tree.getByRole('button', { name: /session/ })).toHaveAttribute('aria-expanded', 'true');
    expect(tree.getByRole('button', { name: /list/ })).toHaveAttribute('aria-expanded', 'false');
    expect(tree.getByText('id').parentElement).toHaveTextContent('id: "S1"');
    expect(tree.getByText('count').parentElement).toHaveTextContent('count: 3');
    expect(tree.getByText('ok').parentElement).toHaveTextContent('ok: true');
    expect(tree.getByText('none').parentElement).toHaveTextContent('none: null');
    expect(tree.getByText('title').parentElement).toHaveTextContent('title: "x"');
    expect(tree.queryByText('alpha')).not.toBeInTheDocument();
  });

  it('opens and closes a branch, and counts its entries', async () => {
    render(<JsonTree data={DOC} />);
    const user = userEvent.setup();
    const list = screen.getByRole('button', { name: /list/ });
    expect(list).toHaveTextContent('[3]');
    await user.click(list);
    expect(list).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('1').parentElement).toHaveTextContent('1: "beta"');
    await user.click(list);
    expect(screen.queryByText('1')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /session/ })).toHaveTextContent('{4}');
  });

  it('says when a branch is empty', async () => {
    render(<JsonTree data={DOC} />);
    await userEvent.setup().click(screen.getByRole('button', { name: /empty/ }));
    expect(screen.getByText('empty', { selector: '.faint' })).toBeInTheDocument();
  });

  it('draws only the first entries of a long list until asked', async () => {
    const data = { rows: Array.from({ length: ARRAY_LIMIT + 10 }, (_, index) => index) };
    render(<JsonTree data={data} openKeys={['rows']} />);
    const user = userEvent.setup();
    expect(document.querySelectorAll('.json-row')).toHaveLength(ARRAY_LIMIT);
    await user.click(screen.getByRole('button', { name: `Show all ${ARRAY_LIMIT + 10} items` }));
    expect(document.querySelectorAll('.json-row')).toHaveLength(ARRAY_LIMIT + 10);
    expect(screen.queryByRole('button', { name: /Show all/ })).not.toBeInTheDocument();
  });
});
