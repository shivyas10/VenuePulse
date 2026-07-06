import type { VenueAnomalies } from "../types";

export default function AnomalyBadges({ anomalies }: { anomalies: VenueAnomalies }) {
  if (!anomalies.sales_drop && !anomalies.void_refund_spike) {
    return <span className="badge badge-ok">Normal</span>;
  }
  return (
    <div className="badge-group">
      {anomalies.sales_drop && <span className="badge badge-warning">Sales drop</span>}
      {anomalies.void_refund_spike && <span className="badge badge-danger">Void/refund spike</span>}
    </div>
  );
}
