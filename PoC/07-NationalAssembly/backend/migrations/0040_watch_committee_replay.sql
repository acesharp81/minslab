ALTER TABLE watch_test_broadcasts
    ADD COLUMN replay_mode text NOT NULL DEFAULT 'SYNTHETIC',
    ADD COLUMN video_embed_url text,
    ADD COLUMN kakao_delivery_enabled boolean NOT NULL DEFAULT false;

ALTER TABLE watch_test_broadcasts
    ADD CONSTRAINT watch_test_replay_mode_check
    CHECK (replay_mode IN ('SYNTHETIC', 'HASI_AI_REPLAY'));

COMMENT ON COLUMN watch_test_broadcasts.replay_mode IS
    'SYNTHETIC: 짧은 가상방송, HASI_AI_REPLAY: 저장된 행안위 AI 발언 구간 재현';
COMMENT ON COLUMN watch_test_broadcasts.kakao_delivery_enabled IS
    '사용자가 재현 시작 시 명시적으로 카카오 실제 발송을 선택했는지 여부';
