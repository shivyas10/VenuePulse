export interface VenueAnomalies {
  sales_drop: boolean;
  void_refund_spike: boolean;
}

export interface VenueSummary {
  venue_id: number;
  venue_name: string;
  total_sales: string;
  sale_count: number;
  anomalies: VenueAnomalies;
}

export interface TopItem {
  item_id: string;
  name: string;
  qty_sold: number;
}

export interface DashboardSnapshot {
  generated_at: string;
  venues: VenueSummary[];
  top_items: TopItem[];
}

export interface HourlyBucket {
  hour: string;
  total_sales: string;
  sale_count: number;
}

export interface VenueDetail {
  venue_id: number;
  venue_name: string;
  hourly_trade: HourlyBucket[];
  top_items: TopItem[];
  void_count: number;
  refund_count: number;
  refund_total: string;
  anomalies: VenueAnomalies;
}
