CREATE TABLE parking_db.parking_usage_baseline (
    baseline_id String,          -- Unique ID for this weekly calculation run
    calculation_date Date,       -- The date this average was computed
    parking_lot_id String,       -- Reference to the lot
    day_of_week UInt8,           -- 1 (Monday) to 7 (Sunday)
    hour_of_day UInt8,           -- 0 to 23
    
    avg_car_count Float64,       -- The "mean" (mu)
    std_dev_car_count Float64,   -- The "standard deviation" (sigma) for Z-score
    max_observed_cars Int32,     -- Useful for capacity planning
    sample_count Int32,          -- How many data points were used for this avg
    
    is_active UInt8 DEFAULT 1    -- Flag to indicate if this is the "current" baseline
) ENGINE = ReplacingMergeTree()
ORDER BY (parking_lot_id, day_of_week, hour_of_day, calculation_date);