import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import AnomalyBadges from "./AnomalyBadges";
import HourlyTradeChart from "./HourlyTradeChart";
import TopItemsPanel from "./TopItemsPanel";

interface Props {
  venueId: number;
  onClose: () => void;
}

export default function VenueDrilldownModal({ venueId, onClose }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["venueDetail", venueId],
    queryFn: () => api.venueDetail(venueId),
  });

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="Close">
          &times;
        </button>

        {isLoading && <p>Loading venue detail...</p>}
        {error && <p className="error-text">Failed to load venue detail.</p>}

        {data && (
          <>
            <div className="modal-header">
              <h2>{data.venue_name}</h2>
              <AnomalyBadges anomalies={data.anomalies} />
            </div>

            <section>
              <h3>Hourly trade (today)</h3>
              <HourlyTradeChart data={data.hourly_trade} />
            </section>

            <div className="modal-columns">
              <section>
                <TopItemsPanel title="What's selling" items={data.top_items} />
              </section>
              <section>
                <h3>Voids &amp; refunds (today)</h3>
                <p>
                  {data.void_count} voids, {data.refund_count} refunds (${data.refund_total} refunded)
                </p>
              </section>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
