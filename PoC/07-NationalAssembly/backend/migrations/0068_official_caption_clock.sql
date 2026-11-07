-- Independent liveness clock: STT and historic recovery cannot mask caption outages.
ALTER TABLE live_broadcasts ADD COLUMN last_official_caption_received_at timestamptz;
UPDATE live_broadcasts SET last_official_caption_received_at = last_caption_received_at
WHERE institution = 'LEGISLATURE' AND active_transcript_source = 'OFFICIAL_CAPTION';
