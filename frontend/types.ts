export type Region = { name: string; latitude: number; longitude: number };
export type Parameters = {
  latitude: number; longitude: number; region_name: string;
  start_year: number; end_year: number; hazard: 'heatwave'; percentile: number; min_duration: number;
};
export type Annual = {
  year: number; event_count: number; heatwave_days: number; mean_duration_days: number;
  longest_event_days: number; mean_intensity_c: number | null; peak_temperature_c: number | null;
  mean_tmax_c: number | null; coverage_pct: number; reliable: boolean;
  rolling_days: number | null; trend_days: number | null;
};
export type Trend = { available: boolean; reason?: string; slope_per_decade?: number; slope_per_year?: number; intercept?: number; r_squared?: number; years_used?: number };
export type ClimateEvent = { start_date: string; end_date: string; duration_days: number; peak_temperature_c: number; mean_exceedance_c: number; peak_exceedance_c: number };
export type Analysis = {
  request: Parameters; algorithm_version: string; generated_at: string;
  cache: { analysis: string; weather: string; storage: string };
  methodology: { threshold_c: number; baseline: string; baseline_coverage_pct: number; definition: string; threshold_scope: string; year_attribution: string; percentile: number; min_duration_days: number };
  summary: { total_events: number; total_heatwave_days: number; longest_event_days: number; mean_event_duration_days: number; peak_temperature_c: number | null; years_analyzed: number; reliable_years: number };
  quality: { expected_days: number; valid_days: number; missing_days: number; coverage_pct: number; excluded_trend_years: number[]; missing_data_policy: string; cleaning: { invalid_values?: number; duplicate_dates?: number; unit_converted?: boolean } };
  source: { provider: string; model: string; kind: string; documentation_url: string; grid_latitude: number; grid_longitude: number; timezone: string; elevation_m: number; attribution: string };
  comparison: { available: boolean; reason?: string; early_period?: string; late_period?: string; early_mean?: number; late_mean?: number; absolute_change?: number; percent_change?: number | null };
  annual: Annual[]; events: ClimateEvent[]; trends: Record<string, Trend>; insights: string[];
};
