from copy import deepcopy
import unittest
from unittest.mock import patch

from app.services.live_group_review import review_request, prompt, apply_review, retain_unassigned
from app.services.live_discussion_classification import classification_request, apply_classification, project_classification


def fixtures():
    turns = [{'utterance_id': str(i), 'summary': text, 'summary_kind': 'AI_CACHED',
              'content_hash': str(i), 'is_final': True, 'first_cursor': i, 'last_cursor': i+1,
              'text': '원문 전문은 외부로 보내지 않음',
              'live_insight': {'topic': text, 'topic_key': text, 'role': 'ANSWER', 'task': '자료 제출 요구'}}
             for i, text in [(1, '미래대응기금의 재원을 논의했다.'),
                             (2, '미래대응기금의 국회 통제를 질의했다.'), (3, '별도 사업을 설명했다.')]]
    req = classification_request(turns, {})
    # Simulate the pre-fix persisted catalog, before local policy rules existed.
    with patch('app.services.live_discussion_classification.canonicalize_state', side_effect=lambda s:s):
        state = apply_classification('bid', {}, req, {'groups': [
            {'id': 'new-1', 'title': '미래대응기금 재원', 'scope': '기금 재원', 'utterance_ids': ['u0']},
            {'id': 'new-2', 'title': '미래대응기금 통제', 'scope': '국회 통제', 'utterance_ids': ['u1']},
            {'id': 'new-3', 'title': '별도 사업', 'scope': '별도 사업', 'utterance_ids': ['u2']}]})
    answer = {'groups': [
        {'title': '미래대응기금', 'scope': '기금 재원과 국회 통제', 'member_ids': ['G001', 'G002']},
        {'title': '별도 사업', 'scope': '별도 사업', 'member_ids': ['G003']}]}
    return turns, state, answer


class LiveGroupReviewTests(unittest.TestCase):
    def test_exact_source_and_assignment_preservation(self):
        turns, state, answer = fixtures(); original = deepcopy(state); original_turns = deepcopy(turns)
        result = apply_review(state, review_request(state, turns), answer)
        self.assertEqual(state, original); self.assertEqual(turns, original_turns)
        self.assertEqual(set(result['assignments']), set(original['assignments']))
        self.assertEqual(len(result['groups']), 2)
        for uid, item in result['assignments'].items():
            self.assertEqual({k:v for k,v in item.items() if k != 'group_id'},
                             {k:v for k,v in original['assignments'][uid].items() if k != 'group_id'})

    def test_missing_duplicate_or_unknown_groups_are_rejected(self):
        turns, state, answer = fixtures(); req = review_request(state, turns)
        for ids in [[], ['G001'], ['G001', 'G001', 'G002'], ['G001', 'unknown']]:
            a = deepcopy(answer); a['groups'][0]['member_ids'] = ids
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                apply_review(state, req, a)

    def test_only_generated_summaries_in_model_input(self):
        turns, state, _ = fixtures()
        self.assertNotIn('원문 전문', prompt(review_request(state, turns)))
        turns[0]['summary_kind'] = 'SOURCE'
        with self.assertRaises(ValueError):
            review_request(state, turns)

    def test_projection_and_incremental_reuse_keep_the_merged_id(self):
        turns, state, answer = fixtures()
        result = apply_review(state, review_request(state, turns), answer)
        project_classification(turns, result)
        first = turns[0]['live_insight']['discussion_group']
        self.assertEqual(first['id'], turns[1]['live_insight']['discussion_group']['id'])
        self.assertEqual(first['title'], '미래대응기금')
        self.assertEqual(classification_request(turns, result)['turns'], [])
        new_turn = deepcopy(turns[0]); new_turn.update(utterance_id='4', first_cursor=4, last_cursor=5, content_hash='4')
        turns.append(new_turn)
        req = classification_request(turns, result)
        updated = apply_classification('bid', result, req, {'groups': [
            {'id': first['id'], 'title': first['title'], 'scope': first['scope'], 'utterance_ids': ['u3']}]})
        self.assertEqual(len(updated['groups']), 2)
        self.assertEqual(updated['assignments']['4']['group_id'], first['id'])

    def test_stale_state_cannot_drop_new_groups(self):
        turns, state, answer = fixtures(); req = review_request(state, turns)
        state['groups']['extra'] = {'title': '추가', 'scope': '추가'}
        state['assignments']['extra'] = {'group_id': 'extra'}
        with self.assertRaises(ValueError):
            apply_review(state, req, answer)

    def test_manual_entry_rejects_unapproved_broadcasts(self):
        from app.ingestion.live_group_repair import process_one
        with self.assertRaisesRegex(ValueError, 'BROADCAST_NOT_APPROVED'):
            process_one('other-broadcast')

    def test_missing_parent_retains_original_without_guessing_or_resending(self):
        turns, state, answer = fixtures();req = review_request(state, turns)
        raw = {'groups': [answer['groups'][0]]};before = deepcopy(raw)
        completed, missing = retain_unassigned(req, raw)
        self.assertEqual(raw, before)
        self.assertEqual(missing, ['G003'])
        self.assertEqual(completed['groups'][-1]['title'], '별도 사업')
        self.assertEqual(len(apply_review(state, req, completed)['assignments']), 3)
        bad = deepcopy(answer);bad['groups'][1]['member_ids'].append('G001')
        with self.assertRaises(ValueError):
            retain_unassigned(req, bad)

    def test_local_policy_rules_preserve_sources_and_retired_ids(self):
        from app.services.live_discussion_classification import canonicalize_state, resolve_group_id
        turns, state, _ = fixtures(); before = deepcopy(state)
        result = canonicalize_state(state)
        self.assertEqual(state, before)
        self.assertEqual(len(result['groups']), 2)
        self.assertEqual(result['local_grouping']['additional_model_calls'], 0)
        self.assertEqual(canonicalize_state(result), result)
        self.assertEqual(result['assignments']['1']['group_id'], result['assignments']['2']['group_id'])
        for uid in state['assignments']:
            self.assertEqual(resolve_group_id(result, state['assignments'][uid]['group_id']), result['assignments'][uid]['group_id'])
            self.assertEqual(result['assignments'][uid]['fingerprint'], state['assignments'][uid]['fingerprint'])

    def test_retired_model_id_reuses_current_catalog_instead_of_recreating(self):
        from app.services.live_discussion_classification import canonicalize_state
        turns, state, _ = fixtures(); result = canonicalize_state(state)
        retired = next(g for g in state['groups'] if g not in result['groups'])
        new = deepcopy(turns[1]);new.update(utterance_id='4', content_hash='4', first_cursor=4, last_cursor=5)
        turns.append(new); req = classification_request(turns, result)
        updated = apply_classification('bid', result, req, {'groups': [
            {'id': retired, **state['groups'][retired], 'utterance_ids': ['u3']}]})
        self.assertEqual(len(updated['groups']), 2)
        self.assertEqual(updated['assignments']['4']['group_id'], result['assignments']['2']['group_id'])

    def test_shared_generic_words_do_not_merge_distinct_projects(self):
        from app.services.live_discussion_classification import canonicalize_state
        state = {'groups': {'a': {'title': '경찰 예산', 'scope': '경찰 예산'},
                            'b': {'title': '소방 예산', 'scope': '소방 예산'},
                            'c': {'title': '지방소멸대응기금', 'scope': '지역 재원'},
                            'd': {'title': '미래대응기금', 'scope': '미래 투자'}},
                 'assignments': {key: {'group_id': key} for key in 'abcd'}}
        self.assertEqual(canonicalize_state(state), state)


if __name__ == '__main__':
    unittest.main()
