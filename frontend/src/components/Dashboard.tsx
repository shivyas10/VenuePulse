import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";
import { api } from "../api/client";
import { useDashboardSocket } from "../hooks/useDashboardSocket";
import type { DashboardSnapshot } from "../types";
import AnomalyBadges from "./AnomalyBadges";
import TopItemsPanel from "./TopItemsPanel";
import VenueDrilldownModal from "./VenueDrilldownModal";

interface Props {
  username: string;
  onLoggedOut: () => void;
}

export default function Dashboard({ username, onLoggedOut }: Props) {
  const queryClient = useQueryClient();
  const [openVenueId, setOpenVenueId] = useState<number | null>(null);
  // Read inside the socket callback without re-subscribing the socket
  // every time the open modal changes.
  const openVenueIdRef = useRef<number | null>(null);
  openVenueIdRef.current = openVenueId;

  const { data, isLoading, error } = useQuery({
    queryKey: ["dashboard"],
    queryFn: api.dashboard,
  });

  const handleSnapshot = useCallback(
    (snapshot: DashboardSnapshot) => {
      queryClient.setQueryData(["dashboard"], snapshot);
      if (openVenueIdRef.current !== null) {
        queryClient.invalidateQueries({ queryKey: ["venueDetail", openVenueIdRef.current] });
      }
    },
    [queryClient],
  );

  useDashboardSocket(handleSnapshot);

  async function handleLogout() {
    await api.logout().catch(() => undefined);
    onLoggedOut();
  }

  if (isLoading) return <div className="centered-message">Loading dashboard...</div>;
  if (error || !data) return <div className="centered-message error-text">Failed to load dashboard.</div>;

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <h1>Ops Dashboard</h1>
        <div className="header-right">
          <span className="updated-at">Updated {new Date(data.generated_at).toLocaleTimeString()}</span>
          <span className="username">{username}</span>
          <button onClick={handleLogout}>Sign out</button>
        </div>
      </header>

      <main className="dashboard-body">
        <section className="venue-list-section">
          <h2>Total sales by venue (today)</h2>
          <table className="venue-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Venue</th>
                <th>Sales</th>
                <th>Transactions</th>
                <th>Flags</th>
              </tr>
            </thead>
            <tbody>
              {data.venues.map((venue, index) => (
                <tr key={venue.venue_id} className="venue-row" onClick={() => setOpenVenueId(venue.venue_id)}>
                  <td>{index + 1}</td>
                  <td>{venue.venue_name}</td>
                  <td>
                    $
                    {Number(venue.total_sales).toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                  </td>
                  <td>{venue.sale_count}</td>
                  <td>
                    <AnomalyBadges anomalies={venue.anomalies} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <aside className="top-items-section">
          <TopItemsPanel title="Top selling items (group-wide)" items={data.top_items} />
        </aside>
      </main>

      {openVenueId !== null && (
        <VenueDrilldownModal venueId={openVenueId} onClose={() => setOpenVenueId(null)} />
      )}
    </div>
  );
}
