'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const speech = require('../web/magazine_speech.js');

function fakeEnvironment() {
  const spoken = [];
  const synth = {
    cancelCount: 0, paused: false,
    speak(utterance) { spoken.push(utterance); utterance.onstart(); },
    cancel() { this.cancelCount += 1; },
    pause() { this.paused = true; },
    resume() { this.paused = false; },
    getVoices() { return [{lang: 'en-US'}, {lang: 'ko-KR', default: true}]; }
  };
  function Utterance(text) { this.text = text; }
  return {synth, spoken, Utterance};
}

test('controller reads segments sequentially with a Korean voice', () => {
  const env = fakeEnvironment();
  const states = [];
  const controller = speech.createController({
    synthesis: env.synth, Utterance: env.Utterance,
    defer(callback) { callback(); },
    onChange(state) { states.push(state); }
  });
  controller.setRate(2);
  assert.equal(controller.start([
    {kind: 'intro', text: '도입'},
    {kind: 'issue', index: 0, text: '첫 이슈'},
    {kind: 'outro', text: '종료'}
  ]), true);
  assert.equal(env.spoken[0].lang, 'ko-KR');
  assert.equal(env.spoken[0].rate, 2);
  env.spoken[0].onend();
  assert.equal(env.spoken[1].text, '첫 이슈');
  assert.equal(controller.getState().currentIssue, 1);
  env.spoken[1].onend();
  env.spoken[2].onend();
  assert.equal(controller.getState().status, 'completed');
  assert.equal(controller.getState().currentIssue, 1);
  assert.ok(states.length > 0);
});

test('controller pauses, resumes, and invalidates canceled callbacks', () => {
  const env = fakeEnvironment();
  const controller = speech.createController({
    synthesis: env.synth, Utterance: env.Utterance, defer(callback) { callback(); }
  });
  controller.start([{kind: 'issue', index: 0, text: '이슈'}]);
  const canceled = env.spoken[0];
  assert.equal(controller.pause(), true);
  assert.equal(controller.getState().status, 'paused');
  assert.equal(controller.resume(), true);
  controller.stop();
  canceled.onend();
  assert.equal(controller.getState().status, 'idle');
});

test('controller accepts the magazine rate set and defaults invalid rates to 1.5', () => {
  const env = fakeEnvironment();
  const controller = speech.createController({synthesis: env.synth, Utterance: env.Utterance});
  assert.equal(controller.getState().rate, 1.5);
  assert.equal(controller.setRate(0.8), 1.5);
  assert.equal(controller.setRate(1.25), 1.25);
  assert.equal(controller.setRate(1.75), 1.75);
  assert.equal(controller.setRate(3), 1.5);
});
