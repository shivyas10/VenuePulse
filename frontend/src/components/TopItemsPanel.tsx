import type { TopItem } from "../types";

interface Props {
  title: string;
  items: TopItem[];
}

export default function TopItemsPanel({ title, items }: Props) {
  return (
    <div className="top-items-panel">
      <h2>{title}</h2>
      {items.length === 0 ? (
        <p className="muted">No sales yet.</p>
      ) : (
        <ol className="top-items-list">
          {items.map((item) => (
            <li key={item.item_id}>
              <span className="item-name">{item.name}</span>
              <span className="item-qty">{item.qty_sold} sold</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
